"""Account-partitioned DynamoDB storage implementing the watch pipeline's Store interface.

Every record operation fixes pk at construction. Request parameters cannot select another
account. One worker per account serializes assessment/dedup; API records use separate keys.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from .models import Disposition, Finding, ScanRun, SourceSnapshot, SystemPassport, utcnow
from .quality import QUALITY_VERSION

MAX_IDENTITY_LENGTH = 256
TENANT_HASH_LENGTH = 64
STALE_JOB_SECONDS = 1200


def tenant_id(identity: str) -> str:
    if not identity or len(identity) > MAX_IDENTITY_LENGTH:
        raise ValueError("Invalid authenticated identity")
    return hashlib.sha256(identity.encode()).hexdigest()


class DynamoStore:
    def __init__(self, table: Any, tenant: str):
        if len(tenant) != TENANT_HASH_LENGTH or any(c not in "0123456789abcdef" for c in tenant):
            raise ValueError("Invalid tenant partition")
        self.table = table
        self.tenant = tenant
        self.pk = "USER#" + tenant

    def close(self) -> None:
        pass

    def get(self, key: str) -> dict | None:
        item = self.table.get_item(Key={"pk": self.pk, "sk": key}, ConsistentRead=True).get("Item")
        return json.loads(item["payload"]) if item else None

    def put(self, key: str, value: dict) -> None:
        self.table.put_item(
            Item={"pk": self.pk, "sk": key, "payload": json.dumps(value, default=str)}
        )

    def delete(self, key: str) -> None:
        self.table.delete_item(Key={"pk": self.pk, "sk": key})

    def items(self, prefix: str) -> list[dict]:
        args = {
            "KeyConditionExpression": Key("pk").eq(self.pk) & Key("sk").begins_with(prefix),
            "ConsistentRead": True,
        }
        out = []
        while True:
            page = self.table.query(**args)
            out.extend(page.get("Items", []))
            if "LastEvaluatedKey" not in page:
                return out
            args["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def models(self, prefix: str, model: Any) -> list:
        return [model.model_validate_json(i["payload"]) for i in self.items(prefix)]

    def register(self) -> None:
        self.table.put_item(Item={"pk": "DIRECTORY", "sk": self.tenant})

    def assessed(self, key: str) -> bool:
        return self.get("assessment#" + hashlib.sha256(key.encode()).hexdigest()) is not None

    def mark_assessed(self, key: str) -> None:
        self.put("assessment#" + hashlib.sha256(key.encode()).hexdigest(), {"done": True})

    def upsert_system(self, passport: SystemPassport) -> None:
        passport.updated_at = utcnow()
        self.put("system#" + passport.id, passport.model_dump(mode="json"))
        self.register()

    def get_system(self, system_id: str) -> SystemPassport | None:
        value = self.get("system#" + system_id)
        return SystemPassport.model_validate(value) if value else None

    def list_systems(self) -> list[SystemPassport]:
        return sorted(self.models("system#", SystemPassport), key=lambda s: s.name)

    def delete_system(self, system_id: str) -> bool:
        exists = self.get_system(system_id) is not None
        self.delete("system#" + system_id)
        for finding in self.list_findings(system_id=system_id, current_only=False, limit=10000):
            for action in self.dispositions_for(finding.id):
                self.delete("disposition#" + action.id)
            self.delete("finding#" + finding.id)
        return exists

    def add_snapshot(self, snapshot: SourceSnapshot) -> SourceSnapshot:
        self.put("snapshot#" + snapshot.id, snapshot.model_dump(mode="json"))
        if snapshot.succeeded:
            self.put("latest#" + snapshot.source_id, snapshot.model_dump(mode="json"))
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> SourceSnapshot | None:
        value = self.get("snapshot#" + snapshot_id)
        return SourceSnapshot.model_validate(value) if value else None

    def latest_snapshot(self, source_id: str) -> SourceSnapshot | None:
        value = self.get("latest#" + source_id)
        return SourceSnapshot.model_validate(value) if value else None

    def previous_hash(self, source_id: str) -> str | None:
        snap = self.latest_snapshot(source_id)
        return snap.content_hash if snap else None

    def save_run(self, run: ScanRun) -> None:
        self.put("run#" + run.id, run.model_dump(mode="json"))

    def get_run(self, run_id: str) -> ScanRun | None:
        value = self.get("run#" + run_id)
        return ScanRun.model_validate(value) if value else None

    def list_runs(self, limit: int = 20) -> list[ScanRun]:
        return sorted(self.models("run#", ScanRun), key=lambda r: r.started_at, reverse=True)[
            :limit
        ]

    def find_by_dedup(self, dedup_key: str) -> list[Finding]:
        return [f for f in self.models("finding#", Finding) if f.dedup_key() == dedup_key]

    def save_finding(self, finding: Finding) -> tuple[Finding, bool]:
        finding.revision_hash = finding.compute_revision_hash()
        for existing in self.find_by_dedup(finding.dedup_key()):
            if existing.revision_hash == finding.revision_hash:
                return existing, False
        self.put("finding#" + finding.id, finding.model_dump(mode="json"))
        return finding, True

    def get_finding(self, finding_id: str) -> Finding | None:
        value = self.get("finding#" + finding_id)
        return Finding.model_validate(value) if value else None

    def list_findings(
        self,
        system_id: str | None = None,
        relevance: str | None = None,
        current_only: bool = True,
        limit: int = 100,
    ) -> list[Finding]:
        records = sorted(self.models("finding#", Finding), key=lambda f: f.created_at, reverse=True)
        seen = set()
        result = []
        for finding in records:
            # Superseded assessment rules mean a superseded verdict; see store.py.
            if current_only and finding.quality_version < QUALITY_VERSION:
                continue
            if current_only and finding.dedup_key() in seen:
                continue
            seen.add(finding.dedup_key())
            if system_id and finding.system_id != system_id:
                continue
            if relevance and finding.relevance.value != relevance:
                continue
            result.append(finding)
        return result[:limit]

    def add_disposition(self, disposition: Disposition) -> Disposition:
        self.put("disposition#" + disposition.id, disposition.model_dump(mode="json"))
        return disposition

    def dispositions_for(self, finding_id: str) -> list[Disposition]:
        return sorted(
            [d for d in self.models("disposition#", Disposition) if d.finding_id == finding_id],
            key=lambda d: d.created_at,
        )

    def is_disposed(self, dedup_key: str) -> bool:
        return any(
            d.action.value in {"acknowledged", "dismissed"}
            for f in self.find_by_dedup(dedup_key)
            for d in self.dispositions_for(f.id)
        )

    def record_cost(
        self, scan_run_id: str, model_id: str, input_tokens: int, output_tokens: int, cost: float
    ) -> None:
        # Same run ID replaces its prior total: retries never duplicate the charge.
        self.put(
            "cost#" + scan_run_id,
            {
                "day": utcnow().date().isoformat(),
                "month": utcnow().strftime("%Y-%m"),
                "cost": cost,
                "model_id": model_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        )

    def _spent(self, period: str, value: str) -> float:
        return sum(
            float(d["cost"])
            for i in self.items("cost#")
            if (d := json.loads(i["payload"]))[period] == value
        )

    def spent_today(self) -> float:
        return self._spent("day", utcnow().date().isoformat())

    def spent_this_month(self) -> float:
        return self._spent("month", utcnow().strftime("%Y-%m"))

    def reserve_scan(self, now: float, cooldown: int) -> bool:
        try:
            self.table.update_item(
                Key={"pk": self.pk, "sk": "cooldown"},
                UpdateExpression="SET requested_at = :now",
                ConditionExpression="attribute_not_exists(requested_at) OR requested_at < :before",
                ExpressionAttributeValues={
                    ":now": Decimal(str(now)),
                    ":before": Decimal(str(now - cooldown)),
                },
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def clear_cooldown(self) -> None:
        self.delete("cooldown")

    def acquire_lock(self, nonce: str, seconds: int = 720) -> bool:
        now = int(datetime.now(timezone.utc).timestamp())
        try:
            self.table.put_item(
                Item={"pk": self.pk, "sk": "lock", "nonce": nonce, "expires": now + seconds},
                ConditionExpression="attribute_not_exists(pk) OR expires < :now",
                ExpressionAttributeValues={":now": now},
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def release_lock(self, nonce: str) -> None:
        self.table.delete_item(
            Key={"pk": self.pk, "sk": "lock"},
            ConditionExpression="nonce = :nonce",
            ExpressionAttributeValues={":nonce": nonce},
        )

    def job(self) -> dict:
        value = self.get("job") or {"status": "idle"}
        if value.get("status") in {"queued", "running"}:
            age = datetime.now(timezone.utc).timestamp() - value.get(
                "started_at", value.get("requested_at", 0)
            )
            if age > STALE_JOB_SECONDS:
                return {
                    **value,
                    "status": "interrupted",
                    "message": "The check did not finish. You can request another check.",
                }
        return value
