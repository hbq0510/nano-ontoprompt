from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings


class SnapshotError(RuntimeError):
    pass


@dataclass
class SnapshotInfo:
    name: str
    path: Path
    size: int
    created_at: datetime
    engine: str


class DatabaseSnapshotService:
    def __init__(self, database_url: str | None = None, snapshot_dir: str | None = None):
        self.database_url = database_url or settings.database_url
        base_dir = Path(snapshot_dir or settings.db_snapshot_dir).resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir = base_dir

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def list_snapshots(self) -> list[SnapshotInfo]:
        items: list[SnapshotInfo] = []
        for path in sorted(self.snapshot_dir.iterdir(), reverse=True):
            if path.is_file():
                stat = path.stat()
                items.append(
                    SnapshotInfo(
                        name=path.name,
                        path=path,
                        size=stat.st_size,
                        created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        engine=self._infer_engine(path.name),
                    )
                )
        return items

    def create_snapshot(self, label: str | None = None) -> SnapshotInfo:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_label = self._sanitize_label(label)
        prefix = f"{stamp}_{safe_label}_" if safe_label else f"{stamp}_"

        if self.is_sqlite:
            db_path = self._sqlite_path()
            if not db_path.exists():
                raise SnapshotError(f"SQLite database not found: {db_path}")
            target = self.snapshot_dir / f"{prefix}snapshot.sqlite3"
            shutil.copy2(db_path, target)
        else:
            parsed = self._parse_postgres_url()
            target = self.snapshot_dir / f"{prefix}snapshot.dump"
            env = os.environ.copy()
            if parsed["password"]:
                env["PGPASSWORD"] = parsed["password"]
            cmd = [
                "pg_dump",
                "-Fc",
                "-h",
                parsed["host"],
                "-p",
                str(parsed["port"]),
                "-U",
                parsed["user"],
                "-d",
                parsed["dbname"],
                "-f",
                str(target),
            ]
            self._run_command(cmd, env, "create PostgreSQL snapshot")

        return self._snapshot_info(target)

    def restore_snapshot(self, name: str) -> SnapshotInfo:
        snapshot = self.snapshot_dir / name
        if not snapshot.exists():
            raise SnapshotError(f"Snapshot not found: {name}")

        if self.is_sqlite:
            db_path = self._sqlite_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snapshot, db_path)
        else:
            parsed = self._parse_postgres_url()
            env = os.environ.copy()
            if parsed["password"]:
                env["PGPASSWORD"] = parsed["password"]

            terminate_cmd = [
                "psql",
                "-h",
                parsed["host"],
                "-p",
                str(parsed["port"]),
                "-U",
                parsed["user"],
                "-d",
                "postgres",
                "-c",
                (
                    f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname = '{parsed['dbname']}' AND pid <> pg_backend_pid();"
                ),
            ]
            self._run_command(terminate_cmd, env, "terminate PostgreSQL connections")

            restore_cmd = [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "-h",
                parsed["host"],
                "-p",
                str(parsed["port"]),
                "-U",
                parsed["user"],
                "-d",
                parsed["dbname"],
                str(snapshot),
            ]
            self._run_command(restore_cmd, env, "restore PostgreSQL snapshot")

        return self._snapshot_info(snapshot)

    def delete_snapshot(self, name: str) -> None:
        snapshot = self.snapshot_dir / name
        if not snapshot.exists():
            raise SnapshotError(f"Snapshot not found: {name}")
        if not snapshot.is_file():
            raise SnapshotError(f"Snapshot path is invalid: {name}")
        snapshot.unlink()

    def _snapshot_info(self, path: Path) -> SnapshotInfo:
        stat = path.stat()
        return SnapshotInfo(
            name=path.name,
            path=path,
            size=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            engine=self._infer_engine(path.name),
        )

    def _infer_engine(self, name: str) -> str:
        return "sqlite" if name.endswith(".sqlite3") else "postgresql"

    def _sqlite_path(self) -> Path:
        return Path(self.database_url.removeprefix("sqlite:///"))

    def _parse_postgres_url(self) -> dict[str, str | int | None]:
        parsed = urlparse(self.database_url)
        if parsed.scheme not in {"postgresql", "postgresql+psycopg2"}:
            raise SnapshotError(f"Unsupported database URL for snapshots: {self.database_url}")
        dbname = parsed.path.lstrip("/")
        if not dbname:
            raise SnapshotError("Database name missing in PostgreSQL URL")
        return {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 5432,
            "user": parsed.username or "",
            "password": parsed.password,
            "dbname": dbname,
        }

    def _run_command(self, cmd: list[str], env: dict[str, str], action: str) -> None:
        try:
            subprocess.run(cmd, check=True, env=env, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise SnapshotError(f"Required command not found while trying to {action}: {cmd[0]}") from exc
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise SnapshotError(f"Failed to {action}: {detail}") from exc

    def _sanitize_label(self, label: str | None) -> str:
        if not label:
            return ""
        return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in label).strip("_")[:40]


def serialize_snapshot(info: SnapshotInfo) -> dict[str, object]:
    return {
        "name": info.name,
        "size": info.size,
        "created_at": info.created_at.isoformat(),
        "engine": info.engine,
    }
