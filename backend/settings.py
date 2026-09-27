"""Environment-backed configuration for the standalone backend.

The backend is intentionally configured without importing the Studio package, so
the worker process and the HTTP application always resolve the same locations.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


PROJECT_ROOT_ENV = "TWINMARKET_PROJECT_ROOT"
DATA_DIR_ENV = "TWINMARKET_DATA_DIR"
RUNS_DIR_ENV = "TWINMARKET_RUNS_DIR"
REGISTRY_PATH_ENV = "TWINMARKET_REGISTRY_PATH"
ALLOWED_ORIGINS_ENV = "TWINMARKET_ALLOWED_ORIGINS"

DEFAULT_ALLOWED_ORIGINS = ("http://127.0.0.1:5173",)
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resolve_path(value: str | Path, *, base: Path) -> Path:
    """Resolve an environment path, treating relative values as ``base``-relative."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _parse_origins(value: str | None) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_ALLOWED_ORIGINS
    # A comma-separated value is shell and dotenv friendly.  Newlines are also
    # accepted so a multi-line deployment value does not accidentally become one
    # invalid origin.
    return tuple(origin.strip() for origin in value.replace("\n", ",").split(",") if origin.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    """Filesystem and browser-origin configuration shared by app and worker."""

    project_root: Path
    data_dir: Path
    runs_dir: Path
    registry_path: Path
    allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS

    def __post_init__(self) -> None:
        # Direct construction is useful in tests and dependency injection.  Keep
        # it equivalent to `from_env`, including macOS's /var -> /private/var
        # canonicalization.
        object.__setattr__(self, "project_root", Path(self.project_root).expanduser().resolve())
        object.__setattr__(self, "data_dir", Path(self.data_dir).expanduser().resolve())
        object.__setattr__(self, "runs_dir", Path(self.runs_dir).expanduser().resolve())
        object.__setattr__(self, "registry_path", Path(self.registry_path).expanduser().resolve())
        object.__setattr__(self, "allowed_origins", tuple(self.allowed_origins))

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if environ is None else environ
        raw_root = source.get(PROJECT_ROOT_ENV)
        project_root = (
            _resolve_path(raw_root, base=Path.cwd())
            if raw_root
            else DEFAULT_PROJECT_ROOT.resolve()
        )

        raw_data_dir = source.get(DATA_DIR_ENV)
        raw_runs_dir = source.get(RUNS_DIR_ENV)
        raw_registry_path = source.get(REGISTRY_PATH_ENV)
        data_dir = _resolve_path(raw_data_dir, base=project_root) if raw_data_dir else project_root / "data"
        runs_dir = _resolve_path(raw_runs_dir, base=project_root) if raw_runs_dir else project_root / "runs"
        registry_path = (
            _resolve_path(raw_registry_path, base=project_root)
            if raw_registry_path
            else project_root / "backend" / "data" / "runs.sqlite3"
        )
        return cls(
            project_root=project_root.resolve(),
            data_dir=data_dir.resolve(),
            runs_dir=runs_dir.resolve(),
            registry_path=registry_path.resolve(),
            allowed_origins=_parse_origins(source.get(ALLOWED_ORIGINS_ENV)),
        )

    # A descriptive alias is useful to callers that do not care about the
    # concrete source of configuration.
    from_environment = from_env

    def project_path(self, value: str | Path) -> Path:
        """Resolve a configured input path and reject project-root escapes."""
        path = _resolve_path(value, base=self.project_root)
        if not path.is_relative_to(self.project_root):
            raise ValueError("配置路径必须位于项目目录")
        return path

    def input_path(self, value: str | Path) -> Path:
        """Resolve a run input beneath the project or configured data root.

        Model configuration and belief files normally live in ``project_root``;
        the template database may instead live in an explicitly configured,
        external ``data_dir``. Both roots are deployment-controlled settings.
        """
        path = _resolve_path(value, base=self.project_root)
        if not path.is_relative_to(self.project_root) and not path.is_relative_to(self.data_dir):
            raise ValueError("配置路径必须位于项目或数据目录")
        return path

    def data_path(self, *parts: str | Path) -> Path:
        """Return a path below the configured data directory without traversal."""
        path = self.data_dir.joinpath(*parts).resolve()
        if not path.is_relative_to(self.data_dir):
            raise ValueError("数据路径必须位于数据目录")
        return path

    def as_environ(self) -> dict[str, str]:
        """Serialize settings for a detached worker subprocess."""
        return {
            PROJECT_ROOT_ENV: str(self.project_root),
            DATA_DIR_ENV: str(self.data_dir),
            RUNS_DIR_ENV: str(self.runs_dir),
            REGISTRY_PATH_ENV: str(self.registry_path),
            ALLOWED_ORIGINS_ENV: ",".join(self.allowed_origins),
        }


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Build a fresh Settings instance; useful for tests and process startup."""
    return Settings.from_env(environ)


def get_settings() -> Settings:
    """Read the current process environment without retaining stale values."""
    return load_settings()
