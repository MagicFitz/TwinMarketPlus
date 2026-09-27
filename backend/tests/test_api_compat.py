import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.process_manager import ProcessManager
from backend.registry import RunRegistry
from backend.settings import Settings


def create_fixture_settings(root: Path) -> Settings:
    data_dir = root / "data"
    runs_dir = root / "runs"
    (root / "config").mkdir(parents=True)
    (root / "util" / "belief").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    data_dir.mkdir()
    runs_dir.mkdir()

    (root / "config" / "api.yaml").write_text("model_name: fixture-model\n", encoding="utf-8")
    (root / "config" / "api_example.yaml").write_text("model_name: fixture-model\n", encoding="utf-8")
    (root / "config" / "embedding.yaml").write_text("model_name: fixture-embedding\n", encoding="utf-8")
    (root / "util" / "belief" / "belief_1000_0129.csv").write_text("user_id,belief\n1,0\n", encoding="utf-8")
    for name in ("stock_data.csv", "trading_days.csv", "sorted_impact_news.pkl"):
        (data_dir / name).write_text("fixture\n", encoding="utf-8")
    (root / "docs" / "public.md").write_text("---\npublished: true\n---\n# Public\nBODY", encoding="utf-8")

    db = data_dir / "sys_1000.db"
    with sqlite3.connect(db) as connection:
        connection.executescript(
            """
            CREATE TABLE Profiles (
                user_id TEXT, user_type TEXT, location TEXT, gender TEXT,
                bh_disposition_effect_category TEXT, bh_lottery_preference_category TEXT,
                bh_underdiversification_category TEXT, current_cash REAL,
                total_value REAL, return_rate REAL, cur_positions TEXT, created_at TEXT
            );
            CREATE TABLE Strategy (user_id TEXT, strategy TEXT);
            CREATE TABLE StockProfile (
                stock_id TEXT, name TEXT, industry TEXT, weight REAL, description TEXT
            );
            CREATE TABLE StockData (date TEXT, stock_id TEXT, close_price REAL, pct_chg REAL, vol REAL);
            """
        )
        connection.execute(
            "INSERT INTO Profiles VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("1", "retail", "Shanghai", "F", "low", "low", "low", 100.0, 110.0, 0.1, "{}", "2023-06-15"),
        )
        connection.execute("INSERT INTO Strategy VALUES(?, ?)", ("1", "hold"))
        connection.execute("INSERT INTO StockProfile VALUES(?,?,?,?,?)", ("000001", "Fixture", "Bank", 1.0, "fixture asset"))
        connection.execute("INSERT INTO StockData VALUES(?,?,?,?,?)", ("2023-06-15", "000001", 10.0, 1.0, 100.0))

    return Settings(
        project_root=root.resolve(),
        data_dir=data_dir.resolve(),
        runs_dir=runs_dir.resolve(),
        registry_path=(root / "backend" / "data" / "runs.sqlite3").resolve(),
        allowed_origins=("https://frontend.example.test",),
    )


class ApiCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = create_fixture_settings(Path(self.temp.name))
        self.registry = RunRegistry(self.settings.registry_path)
        self.manager = ProcessManager(self.registry, self.settings)
        self.client = TestClient(create_app(self.settings, registry=self.registry, manager=self.manager))

    def tearDown(self):
        self.temp.cleanup()

    def test_control_routes_keep_statuses_and_runtime_response_shape(self):
        response = self.client.post(
            "/api/runs",
            json={
                "name": "API test",
                "run_id": "api-test",
                "config": {"user_count": 1, "config_path": "config/api_example.yaml"},
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "draft")
        manifest = json.loads((self.settings.runs_dir / "api-test" / "manifest.json").read_text())
        self.assertIn("code_version", manifest)
        self.assertIn("market_trading_days", manifest["inputs"])
        self.assertEqual(manifest["command_summary"], "backend.worker -> simulation.py (arguments stored in Registry config)")

        runtime = self.client.get("/api/runs/api-test/runtime")
        self.assertEqual(runtime.status_code, 200)
        self.assertEqual(runtime.json()["run_id"], "api-test")
        self.assertIn("lifecycle", runtime.json())
        failed_resume = self.client.post("/api/runs/api-test/resume")
        self.assertEqual(failed_resume.status_code, 409)
        self.assertIn("error", failed_resume.json())

    def test_legacy_read_routes_keep_their_dtos_and_not_found_status(self):
        catalog = self.client.get("/api/catalog")
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(set(catalog.json()), {"group", "market_range", "inventory", "connections"})

        documentation = self.client.get("/api/documentation")
        self.assertEqual(documentation.status_code, 200)
        self.assertEqual(documentation.json(), {"items": [{"path": "public.md", "title": "Public", "category": "文档", "order": 100}]})
        detail = self.client.get("/api/documentation?path=public.md")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["content"], "# Public\nBODY")
        self.assertEqual(self.client.get("/api/documentation?path=private.md").status_code, 404)

        members = self.client.get("/api/runs/template/agents")
        self.assertEqual(members.status_code, 200)
        self.assertEqual(set(members.json()), {"items", "total", "page"})
        self.assertEqual(members.json()["items"][0]["user_id"], "1")
        detail = self.client.get("/api/runs/template/agents/1")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["strategy"], "hold")

        market = self.client.get("/api/runs/template/market")
        self.assertEqual(market.status_code, 200)
        self.assertEqual(set(market.json()), {"assets", "selected", "prices", "source"})
        self.assertEqual(market.json()["selected"], "000001")

    def test_model_settings_can_be_updated_without_returning_api_keys(self):
        initial = self.client.get("/api/settings/models")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["language"]["model_name"], "fixture-model")
        self.assertEqual(initial.json()["language"]["provider"], "openai")
        self.assertNotIn("api_key", initial.json()["language"])

        saved = self.client.put(
            "/api/settings/models/language",
            json={
                "api_type": "openai",
                "provider": "vllm",
                "model_name": "qwen-test",
                "base_url": "http://127.0.0.1:8000/v1",
                "timeout": 45,
                "api_key": "local-secret",
            },
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["model_name"], "qwen-test")
        self.assertTrue(saved.json()["api_key_configured"])
        self.assertNotIn("api_key", saved.json())
        stored = (self.settings.project_root / "config" / "api.yaml").read_text(encoding="utf-8")
        self.assertIn("local-secret", stored)

        embedding = self.client.put(
            "/api/settings/models/embedding",
            json={
                "provider": "ollama",
                "model_name": "bge-m3",
                "base_url": "http://127.0.0.1:11434",
                "endpoint": "http://127.0.0.1:11434/api/embed",
                "timeout": 60,
                "max_retries": 2,
            },
        )
        self.assertEqual(embedding.status_code, 200)
        self.assertEqual(embedding.json()["endpoint"], "http://127.0.0.1:11434/api/embed")

    def test_model_settings_rejects_invalid_endpoint(self):
        response = self.client.put(
            "/api/settings/models/embedding",
            json={"provider": "ollama", "model_name": "bge", "base_url": "not a URL", "endpoint": ""},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("base_url", response.json()["error"])

    def test_allowed_origin_receives_cors_headers(self):
        origin = "https://frontend.example.test"
        preflight = self.client.options(
            "/api/runs",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(preflight.headers["access-control-allow-origin"], origin)
        self.assertIn("POST", preflight.headers["access-control-allow-methods"])


if __name__ == "__main__":
    unittest.main()
