from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class MigrationReport:
    json_jobs: int
    database_jobs: int
    json_files: int
    database_files: int
    backup_path: str | None


class JobDatabase:
    """SQLite persistence with an idempotent jobs.json import."""

    def __init__(self, root: Path):
        self.root = root
        self.path = root / "media_hub.sqlite3"
        self.json_path = root / "jobs.json"
        self.backup_path = root / "jobs.json.pre-sqlite.bak"
        root.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.session() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    media_mode TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
                CREATE TABLE IF NOT EXISTS media_files (
                    job_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    path TEXT NOT NULL,
                    PRIMARY KEY (job_id, filename),
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    @staticmethod
    def _file_rows(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
        output_dir = Path(payload.get("output_dir") or "")
        rows: list[tuple[str, str, str]] = []
        for filename in payload.get("files") or []:
            rows.append((payload["id"], filename, str(output_dir / filename)))
        input_path = payload.get("input_path")
        if input_path:
            path = Path(input_path)
            if all(filename != path.name for _, filename, _ in rows):
                rows.append((payload["id"], path.name, str(path)))
        return rows

    def migrate_json(self) -> MigrationReport:
        payloads: list[dict[str, Any]] = []
        if self.json_path.is_file():
            loaded = json.loads(self.json_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, list):
                raise ValueError("jobs.json ต้องเป็นรายการงาน")
            payloads = loaded
            if not self.backup_path.exists():
                shutil.copy2(self.json_path, self.backup_path)
        with self.session() as connection:
            for payload in payloads:
                self._upsert(connection, payload)
            database_jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            database_files = connection.execute("SELECT COUNT(*) FROM media_files").fetchone()[0]
        json_files = sum(len(self._file_rows(payload)) for payload in payloads)
        if database_jobs < len({payload["id"] for payload in payloads}):
            raise RuntimeError("จำนวนงานหลัง migration ไม่ครบ")
        return MigrationReport(
            json_jobs=len(payloads),
            database_jobs=database_jobs,
            json_files=json_files,
            database_files=database_files,
            backup_path=str(self.backup_path) if self.backup_path.exists() else None,
        )

    def _upsert(self, connection: sqlite3.Connection, payload: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT INTO jobs(id, status, operation, media_mode, created_at, updated_at, payload)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                operation=excluded.operation,
                media_mode=excluded.media_mode,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                payload=excluded.payload
            """,
            (
                payload["id"],
                payload.get("status", "queued"),
                payload.get("operation", "download"),
                payload.get("media_mode", "audio"),
                payload.get("created_at", ""),
                payload.get("updated_at", ""),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        connection.execute("DELETE FROM media_files WHERE job_id = ?", (payload["id"],))
        connection.executemany(
            "INSERT INTO media_files(job_id, filename, path) VALUES(?, ?, ?)",
            self._file_rows(payload),
        )

    def save(self, payloads: Iterable[dict[str, Any]]) -> None:
        with self.session() as connection:
            for payload in payloads:
                self._upsert(connection, payload)

    def load(self) -> list[dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute("SELECT payload FROM jobs ORDER BY created_at").fetchall()
        return [json.loads(row["payload"]) for row in rows]
