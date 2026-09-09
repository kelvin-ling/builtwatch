"""Provision the email-only Cognito Lite client; no SMS, paid email or hosted domain."""
import json, os
from pathlib import Path
import boto3

s=boto3.Session(region_name='us-east-1')
assert s.client('sts').get_caller_identity()['Account']=='[aws-account-redacted]'
c=s.client('cognito-idp');p=Path('data/cognito-access.json')
if p.exists():
    print('Existing Cognito settings retained.');raise SystemExit
pools=c.list_user_pools(MaxResults=60)['UserPools']
pool=next((x['Id'] for x in pools if x['Name']=='builtwatch-public'),None)
if not pool:
    pool=c.create_user_pool(PoolName='builtwatch-public',UserPoolTier='LITE',
        UsernameAttributes=['email'],AutoVerifiedAttributes=['email'],
        UsernameConfiguration={'CaseSensitive':False},
        Schema=[{'Name':'email','AttributeDataType':'String','Required':True,'Mutable':True}],
        Policies={'PasswordPolicy':{'MinimumLength':12,'RequireUppercase':True,'RequireLowercase':True,'RequireNumbers':True,'RequireSymbols':False}},
        MfaConfiguration='OFF',EmailConfiguration={'EmailSendingAccount':'COGNITO_DEFAULT'},
        AccountRecoverySetting={'RecoveryMechanisms':[{'Priority':1,'Name':'verified_email'}]},
        UserPoolTags={'Project':'BuiltWatch'})['UserPool']['Id']
clients=c.list_user_pool_clients(UserPoolId=pool,MaxResults=60)['UserPoolClients']
client=next((x for x in clients if x['ClientName']=='builtwatch-server'),None)
if client:client=c.describe_user_pool_client(UserPoolId=pool,ClientId=client['ClientId'])['UserPoolClient']
else:
    client=c.create_user_pool_client(UserPoolId=pool,ClientName='builtwatch-server',GenerateSecret=True,
        ExplicitAuthFlows=['ALLOW_USER_PASSWORD_AUTH','ALLOW_REFRESH_TOKEN_AUTH'],
        PreventUserExistenceErrors='ENABLED',EnableTokenRevocation=True,
        AccessTokenValidity=5,IdTokenValidity=5,RefreshTokenValidity=1,
        TokenValidityUnits={'AccessToken':'minutes','IdToken':'minutes','RefreshToken':'days'},
        ReadAttributes=['email','email_verified','sub'],WriteAttributes=['email'])['UserPoolClient']
p.write_text(json.dumps({'pool_id':pool,'client_id':client['ClientId'],'client_secret':client['ClientSecret']}));os.chmod(p,0o600)
print('Cognito Lite email registration configured. Server-only client secret saved privately.')
