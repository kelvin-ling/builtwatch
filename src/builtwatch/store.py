"""SQLite persistence.

Everything BuiltWatch knows survives a restart: passports, every snapshot it ever
fetched, every scan run including the ones that failed, every finding, and every
disposition a person recorded. Findings are addressed by a dedup key so a repeated
scan updates rather than duplicates.

The same schema runs locally and in the deployed Lambda (on an EFS-free, single-file
database in /tmp for ephemeral runs, or DynamoDB via the same interface later).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    Disposition,
    Finding,
    ScanRun,
    SourceSnapshot,
    SystemPassport,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS assessments (
    pair_key TEXT PRIMARY KEY, completed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS systems (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    payload      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    id            TEXT PRIMARY KEY,
    source_id     TEXT NOT NULL,
    retrieved_at  TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    fetch_status  TEXT NOT NULL,
    mode          TEXT NOT NULL,
    payload       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_source ON snapshots(source_id, retrieved_at DESC);

CREATE TABLE IF NOT EXISTS scan_runs (
    id           TEXT PRIMARY KEY,
    started_at   TEXT NOT NULL,
    status       TEXT NOT NULL,
    mode         TEXT NOT NULL,
    payload      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id             TEXT PRIMARY KEY,
    dedup_key      TEXT NOT NULL,
    revision_hash  TEXT NOT NULL,
    scan_run_id    TEXT NOT NULL,
    system_id      TEXT NOT NULL,
    source_id      TEXT NOT NULL,
    relevance      TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    superseded     INTEGER NOT NULL DEFAULT 0,
    payload        TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_findings_dedup
    ON findings(dedup_key, revision_hash);
CREATE INDEX IF NOT EXISTS idx_findings_system ON findings(system_id, created_at DESC);

CREATE TABLE IF NOT EXISTS dispositions (
    id           TEXT PRIMARY KEY,
    finding_id   TEXT NOT NULL,
    action       TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    payload      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dispositions_finding ON dispositions(finding_id);

CREATE TABLE IF NOT EXISTS cost_ledger (
    id            TEXT PRIMARY KEY,
    scan_run_id   TEXT NOT NULL,
    occurred_at   TEXT NOT NULL,
    day           TEXT NOT NULL,
    month         TEXT NOT NULL,
    model_id      TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cost_day ON cost_ledger(day);
CREATE INDEX IF NOT EXISTS idx_cost_month ON cost_ledger(month);
"""


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"not JSON serialisable: {type(obj)}")


def _dump(model: Any) -> str:
    return json.dumps(model.model_dump(mode="json"), default=_json_default)


class Store:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def assessed(self, key: str) -> bool:
        return bool(self.conn.execute(
            "SELECT 1 FROM assessments WHERE pair_key=?", (key,)
        ).fetchone())

    def mark_assessed(self, key: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO assessments VALUES (?,?)",
                          (key, datetime.now(timezone.utc).isoformat()))
        self.conn.commit()

    # -- systems -----------------------------------------------------------------

    def upsert_system(self, passport: SystemPassport) -> None:
        passport.updated_at = datetime.now(timezone.utc)
        self.conn.execute(
            "INSERT INTO systems (id, name, updated_at, payload) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
            "updated_at=excluded.updated_at, payload=excluded.payload",
            (passport.id, passport.name, passport.updated_at.isoformat(), _dump(passport)),
        )
        self.conn.commit()

    def get_system(self, system_id: str) -> SystemPassport | None:
        row = self.conn.execute("SELECT payload FROM systems WHERE id=?", (system_id,)).fetchone()
        return SystemPassport.model_validate_json(row["payload"]) if row else None

    def list_systems(self) -> list[SystemPassport]:
        rows = self.conn.execute("SELECT payload FROM systems ORDER BY name").fetchall()
        return [SystemPassport.model_validate_json(r["payload"]) for r in rows]

    def delete_system(self, system_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM systems WHERE id=?", (system_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # -- snapshots ---------------------------------------------------------------

    def add_snapshot(self, snapshot: SourceSnapshot) -> SourceSnapshot:
        self.conn.execute(
            "INSERT OR REPLACE INTO snapshots "
            "(id, source_id, retrieved_at, content_hash, fetch_status, mode, payload) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                snapshot.id,
                snapshot.source_id,
                snapshot.retrieved_at.isoformat(),
                snapshot.content_hash,
                snapshot.fetch_status.value,
                snapshot.mode,
                _dump(snapshot),
            ),
        )
        self.conn.commit()
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> SourceSnapshot | None:
        row = self.conn.execute(
            "SELECT payload FROM snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()
        return SourceSnapshot.model_validate_json(row["payload"]) if row else None

    def latest_snapshot(self, source_id: str) -> SourceSnapshot | None:
        row = self.conn.execute(
            "SELECT payload FROM snapshots WHERE source_id=? AND fetch_status='ok' "
            "ORDER BY retrieved_at DESC LIMIT 1",
            (source_id,),
        ).fetchone()
        return SourceSnapshot.model_validate_json(row["payload"]) if row else None

    def previous_hash(self, source_id: str) -> str | None:
        snap = self.latest_snapshot(source_id)
        return snap.content_hash if snap else None

    # -- scan runs ---------------------------------------------------------------

    def save_run(self, run: ScanRun) -> None:
        self.conn.execute(
            "INSERT INTO scan_runs (id, started_at, status, mode, payload) VALUES (?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload=excluded.payload",
            (run.id, run.started_at.isoformat(), run.status, run.mode, _dump(run)),
        )
        self.conn.commit()

    def get_run(self, run_id: str) -> ScanRun | None:
        row = self.conn.execute("SELECT payload FROM scan_runs WHERE id=?", (run_id,)).fetchone()
        return ScanRun.model_validate_json(row["payload"]) if row else None

    def list_runs(self, limit: int = 20) -> list[ScanRun]:
        rows = self.conn.execute(
            "SELECT payload FROM scan_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [ScanRun.model_validate_json(r["payload"]) for r in rows]

    # -- findings ----------------------------------------------------------------

    def find_by_dedup(self, dedup_key: str) -> list[Finding]:
        rows = self.conn.execute(
            "SELECT payload FROM findings WHERE dedup_key=? ORDER BY created_at DESC",
            (dedup_key,),
        ).fetchall()
        return [Finding.model_validate_json(r["payload"]) for r in rows]

    def save_finding(self, finding: Finding) -> tuple[Finding, bool]:
        """Insert a finding. Returns (stored_finding, is_new).

        A finding whose (dedup_key, revision_hash) pair already exists is *not* stored
        again — that is the mechanism that keeps a repeated scan quiet. A finding whose
        substance changed gets a new row, and the prior row for that dedup key is marked
        superseded so history stays inspectable.
        """
        finding.revision_hash = finding.compute_revision_hash()
        dedup_key = finding.dedup_key()

        existing = self.conn.execute(
            "SELECT id FROM findings WHERE dedup_key=? AND revision_hash=?",
            (dedup_key, finding.revision_hash),
        ).fetchone()
        if existing:
            row = self.conn.execute(
                "SELECT payload FROM findings WHERE id=?", (existing["id"],)
            ).fetchone()
            return Finding.model_validate_json(row["payload"]), False

        self.conn.execute(
            "UPDATE findings SET superseded=1 WHERE dedup_key=?", (dedup_key,)
        )
        self.conn.execute(
            "INSERT INTO findings (id, dedup_key, revision_hash, scan_run_id, system_id, "
            "source_id, relevance, created_at, superseded, payload) VALUES (?,?,?,?,?,?,?,?,0,?)",
            (
                finding.id,
                dedup_key,
                finding.revision_hash,
                finding.scan_run_id,
                finding.system_id,
                finding.source_id,
                finding.relevance.value,
                finding.created_at.isoformat(),
                _dump(finding),
            ),
        )
        self.conn.commit()
        return finding, True

    def get_finding(self, finding_id: str) -> Finding | None:
        row = self.conn.execute(
            "SELECT payload FROM findings WHERE id=?", (finding_id,)
        ).fetchone()
        return Finding.model_validate_json(row["payload"]) if row else None

    def list_findings(
        self,
        system_id: str | None = None,
        relevance: str | None = None,
        current_only: bool = True,
        limit: int = 100,
    ) -> list[Finding]:
        sql = "SELECT payload FROM findings WHERE 1=1"
        params: list[Any] = []
        if current_only:
            sql += " AND superseded=0"
        if system_id:
            sql += " AND system_id=?"
            params.append(system_id)
        if relevance:
            sql += " AND relevance=?"
            params.append(relevance)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [Finding.model_validate_json(r["payload"]) for r in rows]

    # -- dispositions ------------------------------------------------------------

    def add_disposition(self, disposition: Disposition) -> Disposition:
        self.conn.execute(
            "INSERT INTO dispositions (id, finding_id, action, created_at, payload) "
            "VALUES (?,?,?,?,?)",
            (
                disposition.id,
                disposition.finding_id,
                disposition.action.value,
                disposition.created_at.isoformat(),
                _dump(disposition),
            ),
        )
        self.conn.commit()
        return disposition

    def dispositions_for(self, finding_id: str) -> list[Disposition]:
        rows = self.conn.execute(
            "SELECT payload FROM dispositions WHERE finding_id=? ORDER BY created_at",
            (finding_id,),
        ).fetchall()
        return [Disposition.model_validate_json(r["payload"]) for r in rows]

    def is_disposed(self, dedup_key: str) -> bool:
        """True if any revision of this development was acknowledged or dismissed."""
        rows = self.conn.execute(
            "SELECT d.action FROM dispositions d JOIN findings f ON f.id = d.finding_id "
            "WHERE f.dedup_key=? AND d.action IN ('acknowledged','dismissed')",
            (dedup_key,),
        ).fetchall()
        return bool(rows)

    # -- cost ledger -------------------------------------------------------------

    def record_cost(
        self, scan_run_id: str, model_id: str, input_tokens: int, output_tokens: int, cost: float
    ) -> None:
        now = datetime.now(timezone.utc)
        self.conn.execute(
            "INSERT INTO cost_ledger (id, scan_run_id, occurred_at, day, month, model_id, "
            "input_tokens, output_tokens, cost_usd) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                new_id("cost"),
                scan_run_id,
                now.isoformat(),
                now.date().isoformat(),
                now.strftime("%Y-%m"),
                model_id,
                input_tokens,
                output_tokens,
                cost,
            ),
        )
        self.conn.commit()

    def spent_today(self) -> float:
        day = datetime.now(timezone.utc).date().isoformat()
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM cost_ledger WHERE day=?", (day,)
        ).fetchone()
        return float(row["total"])

    def spent_this_month(self) -> float:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM cost_ledger WHERE month=?", (month,)
        ).fetchone()
        return float(row["total"])
