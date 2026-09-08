"""Deploy separate account API/worker with DynamoDB and a shared model allowance.

Legacy S3 data is retained. New credentials are written only to ignored private data/.
Run --build-only first; deployment always uses that validated dependency package.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import secrets
import zipfile
from pathlib import Path

import boto3
from deploy_lambda import build_zip
from deploy_web import role

ROOT = Path(__file__).resolve().parents[1]
REGION = 'us-east-1'
API = 'builtwatch-accounts-api'
WORKER = 'builtwatch-accounts-worker'
TABLE = 'builtwatch-accounts'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-only',action='store_true')
    args = parser.parse_args()
    archive = ROOT / 'data/accounts.zip'
    if args.build_only:
        data = io.BytesIO(build_zip())
        with zipfile.ZipFile(data,'a',zipfile.ZIP_DEFLATED) as z:
            z.write(ROOT/'infra/accounts_runner.py','accounts_runner.py')
        archive.write_bytes(data.getvalue())
        return
    session = boto3.Session(region_name=REGION)
    account = session.client('sts').get_caller_identity()['Account']
    if account != '[aws-account-redacted]':
        raise RuntimeError('Wrong AWS account')
    ddb,lam,iam,logs = [session.client(x) for x in ['dynamodb','lambda','iam','logs']]
    try:
        ddb.create_table(TableName=TABLE,BillingMode='PAY_PER_REQUEST',
            KeySchema=[{'AttributeName':'pk','KeyType':'HASH'},{'AttributeName':'sk','KeyType':'RANGE'}],
            AttributeDefinitions=[{'AttributeName':x,'AttributeType':'S'} for x in ['pk','sk']])
        ddb.get_waiter('table_exists').wait(TableName=TABLE)
    except ddb.exceptions.ResourceInUseException:
        pass
    if ddb.describe_time_to_live(TableName=TABLE)['TimeToLiveDescription']['TimeToLiveStatus'] == 'DISABLED':
        ddb.update_time_to_live(TableName=TABLE,TimeToLiveSpecification={'Enabled':True,'AttributeName':'expires'})
    ddb.update_continuous_backups(TableName=TABLE,PointInTimeRecoverySpecification={'PointInTimeRecoveryEnabled':True,'RecoveryPeriodInDays':7})
    access_path = ROOT/'data/accounts-access.json'
    saved = json.loads(access_path.read_text()) if access_path.exists() else {'secret':secrets.token_urlsafe(48)}
    # Persist before deployment so an interrupted setup does not rotate the signing key.
    access_path.write_text(json.dumps(saved))
    os.chmod(access_path,0o600)
    worker_arn=f'arn:aws:lambda:{REGION}:{account}:function:{WORKER}'
    env={'BW_TABLE':TABLE,'BW_WORKER':WORKER,'BW_SCREEN_MODEL':'us.amazon.nova-lite-v1:0',
         'BW_ASSESS_MODEL':'us.amazon.nova-pro-v1:0','BW_MAX_RUN_USD':'0.25','BW_MAX_DAY_USD':'0.50',
         'BW_MAX_MONTH_USD':'2.00','BW_MAX_SYSTEMS':'10','BW_MAX_ITERATIONS':'8',
         'BW_REGISTRY':'sources/registry.yaml','BW_REPLAY':'replay'}
    for name in [WORKER,API]:
        statements=[{'Effect':'Allow','Action':['logs:CreateLogStream','logs:PutLogEvents'],
            'Resource':f'arn:aws:logs:{REGION}:{account}:log-group:/aws/lambda/{name}:*'},
            {'Effect':'Allow','Action':['dynamodb:GetItem','dynamodb:PutItem','dynamodb:UpdateItem','dynamodb:DeleteItem','dynamodb:Query'],
             'Resource':f'arn:aws:dynamodb:{REGION}:{account}:table/{TABLE}'}]
        if name == API:
            statements.append({'Effect':'Allow','Action':'lambda:InvokeFunction','Resource':worker_arn})
        else:
            statements.append({'Effect':'Allow','Action':['bedrock:InvokeModel','bedrock:InvokeModelWithResponseStream'],
                'Resource':[f'arn:aws:bedrock:{REGION}:{account}:inference-profile/us.amazon.nova-{m}-v1:0' for m in ['lite','pro']]
                +[f'arn:aws:bedrock:*::foundation-model/amazon.nova-{m}-v1:0' for m in ['lite','pro']]})
        arn=role(iam,name+'-role','lambda.amazonaws.com',{'Version':'2012-10-17','Statement':statements})
        with contextlib.suppress(logs.exceptions.ResourceAlreadyExistsException):
            logs.create_log_group(logGroupName='/aws/lambda/'+name)
        logs.put_retention_policy(logGroupName='/aws/lambda/'+name,retentionInDays=7)
        config=dict(FunctionName=name,Handler='accounts_runner.lambda_handler',Environment={'Variables':{**env,**({'BW_PROXY_SECRET':saved['secret']} if name==API else {})}},Timeout=600 if name==WORKER else 60,MemorySize=512)
        try:
            lam.create_function(**config,Runtime='python3.12',Role=arn,Architectures=['arm64'],Code={'ZipFile':archive.read_bytes()})
            lam.get_waiter('function_active_v2').wait(FunctionName=name)
        except lam.exceptions.ResourceConflictException:
            lam.update_function_code(FunctionName=name,ZipFile=archive.read_bytes())
            lam.get_waiter('function_updated_v2').wait(FunctionName=name)
            lam.update_function_configuration(**config)
            lam.get_waiter('function_updated_v2').wait(FunctionName=name)
        lam.put_function_concurrency(FunctionName=name,ReservedConcurrentExecutions=2 if name==WORKER else 4)
        lam.put_function_event_invoke_config(FunctionName=name,MaximumRetryAttempts=2,MaximumEventAgeInSeconds=900)
        print('Deployed',name,flush=True)
    try:
        url=lam.create_function_url_config(FunctionName=API,AuthType='NONE')['FunctionUrl']
    except lam.exceptions.ResourceConflictException:
        url=lam.get_function_url_config(FunctionName=API)['FunctionUrl']
    # Every HTTP request still needs a fresh server-side HMAC signature.
    for sid,action,extra in [('signed-proxy-url','lambda:InvokeFunctionUrl',{'FunctionUrlAuthType':'NONE'}),('signed-proxy-invoke','lambda:InvokeFunction',{'InvokedViaFunctionUrl':True})]:
        with contextlib.suppress(lam.exceptions.ResourceConflictException):
            lam.add_permission(FunctionName=API,StatementId=sid,Action=action,Principal='*',**extra)
    api_arn=f'arn:aws:lambda:{REGION}:{account}:function:{API}'
    schedule_role=role(iam,API+'-scheduler','scheduler.amazonaws.com',{'Version':'2012-10-17','Statement':[{'Effect':'Allow','Action':'lambda:InvokeFunction','Resource':api_arn}]})
    sch=session.client('scheduler')
    config={'Name':'builtwatch-accounts-daily','ScheduleExpression':'cron(0 7 * * ? *)','ScheduleExpressionTimezone':'America/Toronto','State':'ENABLED','FlexibleTimeWindow':{'Mode':'OFF'},
            'Target':{'Arn':api_arn,'RoleArn':schedule_role,'Input':'{"task":"daily"}','RetryPolicy':{'MaximumRetryAttempts':0,'MaximumEventAgeInSeconds':900}}}
    try:
        sch.create_schedule(**config)
    except sch.exceptions.ConflictException:
        sch.update_schedule(**config)
    access_path.write_text(json.dumps({**saved,'url':url}))
    print('Account backend and daily schedule ready. Private connection settings saved.',flush=True)


if __name__ == '__main__':
    main()
