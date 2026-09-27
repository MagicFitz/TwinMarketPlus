import tempfile
import unittest
from pathlib import Path

from backend.settings import (
    ALLOWED_ORIGINS_ENV,
    DATA_DIR_ENV,
    PROJECT_ROOT_ENV,
    REGISTRY_PATH_ENV,
    RUNS_DIR_ENV,
    Settings,
)
from backend.run_service import normalize_config


class SettingsTests(unittest.TestCase):
    def test_environment_controls_every_backend_location_and_origin(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings = Settings.from_env(
                {
                    PROJECT_ROOT_ENV: str(root),
                    DATA_DIR_ENV: "external-data",
                    RUNS_DIR_ENV: "var/runs",
                    REGISTRY_PATH_ENV: "var/registry.sqlite3",
                    ALLOWED_ORIGINS_ENV: "http://localhost:5173, https://studio.example.test\nhttp://127.0.0.1:4173",
                }
            )

            self.assertEqual(settings.project_root, root.resolve())
            self.assertEqual(settings.data_dir, (root / "external-data").resolve())
            self.assertEqual(settings.runs_dir, (root / "var" / "runs").resolve())
            self.assertEqual(settings.registry_path, (root / "var" / "registry.sqlite3").resolve())
            self.assertEqual(
                settings.allowed_origins,
                ("http://localhost:5173", "https://studio.example.test", "http://127.0.0.1:4173"),
            )
            self.assertEqual(settings.as_environ()[REGISTRY_PATH_ENV], str(settings.registry_path))

    def test_external_data_directory_becomes_the_default_template_input(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as data_folder:
            root = Path(folder)
            data_dir = Path(data_folder)
            settings = Settings(
                project_root=root.resolve(),
                data_dir=data_dir.resolve(),
                runs_dir=(root / "runs").resolve(),
                registry_path=(root / "registry.sqlite3").resolve(),
            )
            config = normalize_config({}, settings)
            self.assertEqual(config["template_db"], str((data_dir / "sys_1000.db").resolve()))


if __name__ == "__main__":
    unittest.main()
