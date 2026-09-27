import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.services.agents import AgentService
from backend.services.logs import clean_log, config_from_log, read_logs
from backend.services.read_only import ReadOnlyStore, UnknownRunError, WorkspacePathError
from backend.settings import Settings


def settings_for(root: Path, *, data_dir: Path | None = None) -> Settings:
    data = (data_dir or root / "data").resolve()
    runs = (root / "runs").resolve()
    data.mkdir(parents=True, exist_ok=True)
    runs.mkdir(parents=True, exist_ok=True)
    return Settings(
        project_root=root.resolve(),
        data_dir=data,
        runs_dir=runs,
        registry_path=(root / "backend" / "data" / "runs.sqlite3").resolve(),
    )


class ReadOnlyTests(unittest.TestCase):
    def test_read_only_connection_blocks_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings = settings_for(root)
            path = settings.data_dir / "test.db"
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE sample(value INTEGER)")
                connection.execute("INSERT INTO sample VALUES (7)")

            store = ReadOnlyStore(settings)
            self.assertEqual(store.scalar(path, "SELECT value FROM sample"), 7)
            with self.assertRaises(sqlite3.OperationalError):
                store.rows(path, "DELETE FROM sample")
            self.assertEqual(store.scalar(path, "SELECT count(*) FROM sample"), 1)

    def test_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = ReadOnlyStore(settings_for(root))
            with self.assertRaises(WorkspacePathError):
                store.local(root / ".." / "outside.sqlite3")

    def test_missing_database_is_not_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ReadOnlyStore(settings_for(Path(folder)))
            with self.assertRaises(FileNotFoundError):
                store.rows(None, "SELECT 1")

    def test_unknown_resource_cannot_be_an_arbitrary_path(self):
        with tempfile.TemporaryDirectory() as folder:
            service = AgentService(settings_for(Path(folder)))
            with self.assertRaises(UnknownRunError):
                service.get_db("../../etc/passwd")

    def test_registry_output_directory_must_stay_inside_runs_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = ReadOnlyStore(settings_for(root))
            with self.assertRaises(UnknownRunError):
                store.resolve_run_folder("safe-run", root / "outside")

    def test_config_allowlist_drops_credentials(self):
        config = config_from_log(
            "=== 模拟配置参数 ===\n"
            + json.dumps(
                {
                    "start_date": "2023-06-15",
                    "api_key": "SECRET",
                    "base_url": "private",
                    "node": 10,
                }
            )
        )
        self.assertEqual(config, {"start_date": "2023-06-15", "node": 10})

    def test_logs_drop_model_text_and_concatenated_http_details(self):
        lines = clean_log(
            "model response SECRET\n"
            "处理输入 2023-06-21: 13%|text| HTTP Request: token SECRET\n"
            "=== 当前日期: 2023-06-21 === secret\n"
            "交易日: True\n"
        )
        self.assertEqual(lines, ["处理输入 2023-06-21: 13%", "=== 当前日期: 2023-06-21 ===", "交易日: True"])
        self.assertNotIn("SECRET", json.dumps(lines))

    def test_log_reader_returns_the_legacy_paged_dto(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings = settings_for(root)
            output = settings.runs_dir / "safe-run"
            output.mkdir()
            (output / "simulation.log").write_text("交易日: True\nmodel response SECRET\n", encoding="utf-8")
            self.assertEqual(
                read_logs(settings, output, page=1, page_size=100),
                {"items": ["交易日: True"], "page": 1, "page_size": 100, "total": 1},
            )

    def test_external_configured_data_directory_is_a_trusted_read_root(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as data_folder:
            root = Path(folder)
            data_dir = Path(data_folder)
            settings = settings_for(root, data_dir=data_dir)
            path = data_dir / "readable.db"
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE sample(value INTEGER)")
                connection.execute("INSERT INTO sample VALUES (9)")

            self.assertEqual(ReadOnlyStore(settings).scalar(path, "SELECT value FROM sample"), 9)


if __name__ == "__main__":
    unittest.main()
