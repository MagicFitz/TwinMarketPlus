"""Safe, framework-independent access to TwinMarket's local read models.

The HTTP layer supplies a :class:`backend.settings.Settings` instance.  This
module intentionally has no FastAPI or Studio dependency so the same guards
are used by catalog, documentation, Agent, Market, and log services.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable

from backend.settings import Settings


class WorkspacePathError(ValueError):
    """Raised when a requested path escapes the configured trusted roots."""


class UnknownRunError(KeyError):
    """Raised when a non-template run cannot be resolved safely."""


class ReadOnlyStore:
    """Resolve local files and execute SQLite queries without write access."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.project_root = Path(settings.project_root).resolve()
        self.data_dir = Path(settings.data_dir).resolve()
        self.runs_dir = Path(settings.runs_dir).resolve()
        self._roots = tuple(dict.fromkeys((self.project_root, self.data_dir, self.runs_dir)))

    @staticmethod
    def _under(path: Path, root: Path) -> bool:
        return path == root or path.is_relative_to(root)

    def local(self, path: Path | str) -> Path:
        """Return a resolved path only when it remains in a configured root."""
        resolved = Path(path).resolve()
        if not any(self._under(resolved, root) for root in self._roots):
            raise WorkspacePathError("Path is outside the workspace")
        return resolved

    def rows(self, db: Path | str | None, sql: str, values: Iterable[Any] = ()) -> list[dict[str, Any]]:
        """Execute a query against an existing SQLite file in read-only mode."""
        if db is None:
            raise FileNotFoundError("Data source is unavailable")
        path = self.local(db)
        if not path.is_file():
            raise FileNotFoundError("Data source is unavailable")
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            return [dict(row) for row in connection.execute(sql, tuple(values))]

    def scalar(self, db: Path | str | None, sql: str, values: Iterable[Any] = ()) -> Any:
        result = self.rows(db, sql, values)
        return next(iter(result[0].values())) if result else None

    def database(self, folder: Path | str, pattern: str) -> Path | None:
        """Find the first real database matching a service-owned glob pattern."""
        resolved_folder = self.local(folder)
        if not resolved_folder.is_dir():
            return None
        for candidate in sorted(resolved_folder.glob(pattern)):
            try:
                resolved = self.local(candidate)
            except WorkspacePathError:
                # A symlink which escapes a trusted root is never a data source.
                continue
            if resolved.is_file():
                return resolved
        return None

    @staticmethod
    def _safe_run_id(run_id: str) -> bool:
        candidate = Path(run_id)
        return bool(run_id) and candidate.name == run_id and run_id not in {".", ".."}

    def resolve_run_folder(self, run_id: str, output_dir: Path | str | None = None) -> Path:
        """Resolve a registry output folder, current runs folder, or old ``logs_*`` folder.

        ``output_dir`` is supplied from a Registry record by the HTTP layer.  It
        is accepted only beneath ``runs_dir``; this prevents a compromised
        registry row from turning a read endpoint into arbitrary-file access.
        Without it, direct children of ``runs_dir`` are supported for the
        registry-style layout, followed by the historical top-level ``logs_*``
        layout used by ``studio/server.py``.
        """
        if not isinstance(run_id, str) or not self._safe_run_id(run_id):
            raise UnknownRunError(run_id)

        if output_dir is not None:
            try:
                candidate = self.local(output_dir)
            except WorkspacePathError as error:
                raise UnknownRunError(run_id) from error
            if not candidate.is_relative_to(self.runs_dir) or candidate == self.runs_dir or not candidate.is_dir():
                raise UnknownRunError(run_id)
            return candidate

        try:
            candidate = self.local(self.runs_dir / run_id)
        except WorkspacePathError as error:
            raise UnknownRunError(run_id) from error
        if candidate.is_relative_to(self.runs_dir) and candidate != self.runs_dir and candidate.is_dir():
            return candidate

        # The pre-Registry adapter only exposed top-level directories named
        # ``logs_*``.  Preserve that narrow compatibility boundary, rather than
        # interpreting arbitrary project-root directory names as run IDs.
        if run_id.startswith("logs_"):
            try:
                legacy = self.local(self.project_root / run_id)
            except WorkspacePathError as error:
                raise UnknownRunError(run_id) from error
            if legacy.is_dir():
                return legacy
        raise UnknownRunError(run_id)


def local(settings: Settings, path: Path | str) -> Path:
    return ReadOnlyStore(settings).local(path)


def rows(settings: Settings, db: Path | str | None, sql: str, values: Iterable[Any] = ()) -> list[dict[str, Any]]:
    return ReadOnlyStore(settings).rows(db, sql, values)


def scalar(settings: Settings, db: Path | str | None, sql: str, values: Iterable[Any] = ()) -> Any:
    return ReadOnlyStore(settings).scalar(db, sql, values)


def database(settings: Settings, folder: Path | str, pattern: str) -> Path | None:
    return ReadOnlyStore(settings).database(folder, pattern)


def resolve_run_folder(settings: Settings, run_id: str, output_dir: Path | str | None = None) -> Path:
    return ReadOnlyStore(settings).resolve_run_folder(run_id, output_dir)
