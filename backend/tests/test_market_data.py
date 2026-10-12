"""Offline tests for the complete provider -> snapshot -> pinned run contract."""
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
import requests
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.market_data.assets import load_assets
from backend.market_data.errors import MarketError
from backend.market_data.indices import build_indices, ratio
from backend.market_data.providers.tushare import FIELDS, TushareProvider
from backend.market_data.registry import MarketRegistry
from backend.market_data.snapshots import fingerprint, resolve_snapshot
from backend.registry import RunRegistry
from backend.run_service import create_run, validate_start
from backend.services.market_sync import MarketSyncService
from backend.settings import Settings
from script.market_inputs import EmptyNewsIndex, news_for_date, open_trading_dates
from script.prepare_simulation_run import STOCK_COLUMNS, prepare_database

ROOT = Path(__file__).resolve().parents[2]
SECRET = "market-secret-canary"


class FakeTushare:
    def __init__(self, data_dir, *, denied=False, incomplete=False):
        self.assets = load_assets(data_dir / "market_assets.yaml")[0]["assets"]
        self.codes = [c["ts_code"] for asset in self.assets.values() for c in asset["constituents"]]
        self.calendar = pd.read_csv(data_dir / "trading_days.csv").to_dict("records")
        previous = "2025-01-10"
        for day in pd.date_range("2025-01-11", "2025-01-14"):
            opened = day.weekday() < 5
            self.calendar.append({"cal_date": day.strftime("%Y-%m-%d"), "is_open": "open" if opened else "close", "pretrade_date": previous})
            if opened:
                previous = day.strftime("%Y-%m-%d")
        self.denied, self.incomplete = denied, incomplete
        self.calls = []

    def post(self, url, **kwargs):
        body = kwargs["json"]
        self.calls.append(body)
        api, params = body["api_name"], body["params"]
        if api == "daily_basic" and self.denied:
            return SimpleNamespace(status_code=200, json=lambda: {"code": 2002, "msg": f"无权限 {SECRET}"})
        if api == "trade_cal":
            rows = [{"cal_date": row["cal_date"].replace("-", ""), "is_open": 1 if row["is_open"] == "open" else 0,
                     "pretrade_date": row["pretrade_date"].replace("-", "")} for row in self.calendar
                    if params["start_date"] <= row["cal_date"].replace("-", "") <= params["end_date"]]
        else:
            rows = []
            codes = self.codes[:1] if self.incomplete else self.codes
            for code in codes:
                if api == "daily":
                    rows.append({"ts_code": code, "trade_date": params.get("trade_date", "20250114"), "close": 101,
                                 "pre_close": 100, "pct_chg": 1, "vol": 10, "amount": 2})
                else:
                    rows.append({"ts_code": code, "trade_date": params.get("trade_date", "20250114"),
                                 "pe_ttm": 20, "pb": 2, "ps_ttm": 4, "dv_ttm": 3})
            if "ts_code" in params:
                rows = [row for row in rows if row["ts_code"] == params["ts_code"]]
        names = FIELDS[api].split(",")
        payload = {"code": 0, "data": {"fields": names, "items": [[row[key] for key in names] for row in rows]}}
        return SimpleNamespace(status_code=200, json=lambda: payload)

    def provider(self):
        return TushareProvider(SECRET, post=self.post, sleep=lambda duration: None, interval=0)


class MarketFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.env = patch.dict(os.environ, {"TUSHARE_TOKEN": ""})
        self.env.start()
        data = self.root / "data"
        data.mkdir()
        for name in ("stock_data.csv", "trading_days.csv", "stock_profile.csv", "market_assets.yaml"):
            shutil.copyfile(ROOT / "data" / name, data / name)
        pd.DataFrame({"cal_date": ["2025-01-10"], "news": [["old news must not leak"]]}).to_pickle(data / "sorted_impact_news.pkl")
        (self.root / "config").mkdir()
        (self.root / "config" / "api.yaml").write_text("model_name: fixture\n")
        (self.root / "util" / "belief").mkdir(parents=True)
        (self.root / "util" / "belief" / "belief_1000_0129.csv").write_text("user_id,belief\n1,0.5\n")
        with sqlite3.connect(data / "sys_1000.db") as db:
            db.executescript("CREATE TABLE Profiles(user_id TEXT,created_at TEXT); CREATE TABLE Strategy(user_id TEXT,strategy TEXT); CREATE TABLE TradingDetails(user_id TEXT);")
            db.execute("INSERT INTO Profiles VALUES ('1','2023-06-14 00:00:00')")
            db.execute("INSERT INTO Strategy VALUES ('1','hold')")
            db.execute("CREATE TABLE StockData(" + ",".join(column + " " + ("TEXT" if column in {"stock_id", "date"} else "REAL") for column in STOCK_COLUMNS) + ")")
        self.settings = Settings(self.root, data, self.root / "runs", self.root / "backend" / "data" / "runs.sqlite3")
        self.service = MarketSyncService(self.settings)
        self.service.source.update({"token": SECRET})
        self.fake = FakeTushare(data)
        self.baseline_hash = fingerprint(data / "stock_data.csv")

    def tearDown(self):
        self.env.stop()
        self.temporary.cleanup()

    def request(self, **changes):
        return {"mode": "backfill", "start_date": "2025-01-13", "end_date": "2025-01-14", "allow_missing_news": True, **changes}

    def sync(self, fake=None, **changes):
        job = self.service.create(self.request(**changes), launch=False)
        result = self.service.execute(job["job_id"], (fake or self.fake).provider())
        self.assertEqual(result["status"], "completed", result)
        return result, self.service.registry.snapshot(result["snapshot_id"])


class ProviderTests(unittest.TestCase):
    def provider(self, post):
        return TushareProvider(SECRET, post=post, sleep=lambda duration: None, interval=0)

    def response(self, payload, status=200):
        return SimpleNamespace(status_code=status, json=lambda: payload)

    def test_permission_does_not_retry_or_expose_supplier_message(self):
        post = Mock(return_value=self.response({"code": 2002, "msg": "无权限 " + SECRET}))
        with self.assertRaises(MarketError) as caught:
            self.provider(post).query("daily", {})
        self.assertEqual(caught.exception.code, "TUSHARE_PERMISSION_DENIED")
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertEqual(post.call_count, 1)

    def test_invalid_token_and_malformed_responses_are_stable_errors(self):
        for payload, code in (({"code": 2002, "msg": "token invalid " + SECRET}, "TUSHARE_AUTH_FAILED"),
                              ({"code": 0, "data": {"fields": ["ts_code"], "items": [[1, 2]]}}, "TUSHARE_INVALID_RESPONSE"),
                              ({"code": 0}, "TUSHARE_INVALID_RESPONSE")):
            with self.subTest(code=code), self.assertRaises(MarketError) as caught:
                self.provider(Mock(return_value=self.response(payload))).query("daily", {})
            self.assertEqual(caught.exception.code, code)

    def test_transient_errors_retry_and_empty_success_is_valid(self):
        empty = self.response({"code": 0, "data": {"fields": FIELDS["daily"].split(","), "items": []}})
        for first in (requests.Timeout(SECRET), self.response({}, status=503), self.response({"code": 2002, "msg": "每分钟最多访问"})):
            post = Mock(side_effect=[first, empty])
            self.assertEqual(self.provider(post).query("daily", {}), [])
            self.assertEqual(post.call_count, 2)

    def test_exhausted_retry_does_not_expose_network_exception(self):
        post = Mock(side_effect=requests.Timeout(SECRET))
        with self.assertRaises(MarketError) as caught:
            self.provider(post).query("daily", {})
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertEqual(post.call_count, 4)

    def test_pagination_refuses_silent_repeated_page(self):
        names = FIELDS["daily"].split(",")
        payload = {"code": 0, "data": {"fields": names, "items": [[str(i), "20250113", 10, 10, 0, 1, 1] for i in range(6000)]}}
        with self.assertRaises(MarketError) as caught:
            self.provider(Mock(return_value=self.response(payload))).fetch("daily", {})
        self.assertEqual(caught.exception.code, "DATA_DUPLICATE_ROWS")


class SnapshotTests(MarketFixture):
    def test_source_secret_keep_replace_clear_and_environment_priority(self):
        source = self.service.source
        self.assertEqual(source.token(), SECRET)
        self.assertNotIn(SECRET, json.dumps(source.get()))
        self.assertEqual(source.path.stat().st_mode & 0o777, 0o600)
        source.update({"enabled": False})
        self.assertEqual(source.token(), SECRET)
        source.update({"enabled": True, "token": "replacement"})
        self.assertEqual(source.token(), "replacement")
        with patch.dict(os.environ, {"TUSHARE_TOKEN": "environment-secret"}):
            source.update({"token": ""})
            self.assertEqual(source.token(), "environment-secret")
            self.assertEqual(source.get()["credential_source"], "environment")
        self.assertFalse(source.get()["token_configured"])

    def test_capabilities_are_separate_and_invalidated_on_secret_update(self):
        fake = FakeTushare(self.settings.data_dir, denied=True)
        result = self.service.source.test(fake.provider())
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["capabilities"]["daily_basic"]["status"], "permission_denied")
        self.assertNotIn(SECRET, json.dumps(result))
        self.service.source.update({"token": "new-token"})
        self.assertEqual(self.service.source.get()["status"], "untested")

    def test_snapshot_units_chaining_fingerprints_and_news_containers(self):
        job, metadata = self.sync()
        _, folder = resolve_snapshot(self.settings, metadata["snapshot_id"], allow_missing_news=True)
        frame = pd.read_csv(folder / "stock_data.csv")
        before = pd.read_csv(self.settings.data_dir / "stock_data.csv")
        price = before[(before.ts_code == "TLEI") & (before.date == "2025-01-10")].iloc[0]["close"]
        new = frame[(frame.ts_code == "TLEI") & (frame.date >= "2025-01-13")]
        self.assertAlmostEqual(new.iloc[0]["close"], price * 1.01)
        self.assertAlmostEqual(new.iloc[1]["close"], price * 1.01 ** 2)
        self.assertEqual(new.iloc[0]["vol"], 2000)
        self.assertEqual(new.iloc[0]["amount"], 4000)
        self.assertEqual(new.iloc[0]["pe_ttm"], 20)
        self.assertTrue(pd.isna(new.iloc[0]["elg_amount_net"]))
        news = pd.read_pickle(folder / "sorted_impact_news.pkl")
        self.assertEqual(len(news), len(pd.date_range(metadata["start_date"], "2025-01-14")))
        self.assertTrue(all(item == [] for item in news.news))
        self.assertEqual(self.baseline_hash, fingerprint(self.settings.data_dir / "stock_data.csv"))
        self.assertIsNone(self.service.registry.setting("active_snapshot_id"))
        self.assertEqual(folder.joinpath("stock_data.csv").stat().st_mode & 0o222, 0)
        self.assertNotIn(SECRET, self.service.registry.path.read_bytes().decode(errors="ignore"))
        for file in folder.rglob("*"):
            if file.is_file() and file.suffix not in {".gz", ".pkl"}:
                self.assertNotIn(SECRET, file.read_text())
        self.assertEqual(job["progress"], 1)

    def test_optional_permission_degrades_but_incomplete_required_data_cannot_publish(self):
        _, metadata = self.sync(FakeTushare(self.settings.data_dir, denied=True))
        self.assertEqual(metadata["datasets"]["daily_basic"]["status"], "missing")
        job = self.service.create(self.request(), launch=False)
        result = self.service.execute(job["job_id"], FakeTushare(self.settings.data_dir, incomplete=True).provider())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "DATA_COVERAGE_INCOMPLETE")
        self.assertEqual(len(self.service.registry.snapshots()), 1)

    def test_cancel_conflict_and_restart_persistence(self):
        job = self.service.create(self.request(), launch=False)
        with self.assertRaises(MarketError) as caught:
            self.service.create(self.request(), launch=False)
        self.assertEqual(caught.exception.code, "SYNC_JOB_CONFLICT")
        self.service.registry.cancel(job["job_id"])
        self.assertEqual(self.service.execute(job["job_id"], self.fake.provider())["status"], "cancelled")
        self.assertEqual(MarketRegistry(self.settings).job(job["job_id"])["status"], "cancelled")
        self.assertFalse(self.service.registry.snapshots())

    def test_cancel_during_fetch_never_publishes(self):
        job = self.service.create(self.request(), launch=False)
        original = self.fake.post
        def cancel(url, **kwargs):
            if kwargs["json"]["api_name"] == "daily":
                self.service.registry.cancel(job["job_id"])
            return original(url, **kwargs)
        result = self.service.execute(job["job_id"], TushareProvider(SECRET, post=cancel, interval=0))
        self.assertEqual(result["status"], "cancelled")
        self.assertFalse(self.service.registry.snapshots())

    def test_duplicate_sync_produces_new_snapshot_without_mutating_old(self):
        _, first = self.sync()
        _, second = self.sync()
        self.assertNotEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertEqual(resolve_snapshot(self.settings, first["snapshot_id"], allow_missing_news=True)[0], first)

    def test_run_pinning_private_history_and_default_changes(self):
        _, first = self.sync()
        self.service.activate(first["snapshot_id"])
        registry = RunRegistry(self.settings.registry_path)
        run = create_run(registry, {"name": "snapshot-run", "config": {"start_date": "2025-01-13", "end_date": "2025-01-14", "allow_missing_news": True}}, self.settings)
        self.assertEqual(run["config"]["market_snapshot_id"], first["snapshot_id"])
        manifest = json.loads((Path(run["output_dir"]) / "manifest.json").read_text())
        self.assertEqual(manifest["market_environment"]["snapshot_id"], first["snapshot_id"])
        _, folder = resolve_snapshot(self.settings, first["snapshot_id"], allow_missing_news=True)
        private = Path(run["output_dir"]) / "user.db"
        prepare_database(self.settings.data_dir / "sys_1000.db", private, 1, market_snapshot=folder, start_date="2025-01-13")
        with sqlite3.connect(private) as db:
            self.assertEqual(db.execute("SELECT max(date) FROM StockData").fetchone()[0], "2025-01-10")
            self.assertGreaterEqual(db.execute("SELECT count(DISTINCT date) FROM StockData").fetchone()[0], 30)
            self.assertEqual(db.execute("SELECT created_at FROM Profiles").fetchone()[0], "2025-01-12 00:00:00")
        _, second = self.sync()
        self.service.activate(second["snapshot_id"])
        self.assertEqual(registry.get(run["run_id"])["config"]["market_snapshot_id"], first["snapshot_id"])
        self.assertEqual(validate_start(run, settings=self.settings), [])

    def test_outside_coverage_news_opt_in_and_tampered_snapshot_block_run(self):
        _, metadata = self.sync()
        for start, end, allow, code in (("2025-01-13", "2025-01-15", True, "SNAPSHOT_RANGE_UNCOVERED"),
                                        ("2025-01-13", "2025-01-14", False, "NEWS_MISSING_NOT_ALLOWED")):
            with self.assertRaises(MarketError) as caught:
                resolve_snapshot(self.settings, metadata["snapshot_id"], start_date=start, end_date=end, allow_missing_news=allow)
            self.assertEqual(caught.exception.code, code)
        _, folder = resolve_snapshot(self.settings, metadata["snapshot_id"], allow_missing_news=True)
        stock = folder / "stock_data.csv"
        stock.chmod(0o644)
        stock.write_text("tampered")
        with self.assertRaises(MarketError) as caught:
            self.service.activate(metadata["snapshot_id"])
        self.assertEqual(caught.exception.code, "SNAPSHOT_INTEGRITY_FAILED")

    def test_worker_passes_snapshot_to_preparation_and_simulation_without_provider_token(self):
        from backend.worker import run_worker
        _, metadata = self.sync()
        registry = RunRegistry(self.settings.registry_path)
        run = create_run(registry, {"name": "worker-run", "config": {"start_date": "2025-01-13", "end_date": "2025-01-14",
            "market_snapshot_id": metadata["snapshot_id"], "allow_missing_news": True}}, self.settings)
        registry.transition(run["run_id"], "queued")
        with patch.dict(os.environ, {"TUSHARE_TOKEN": SECRET}), patch("backend.worker.subprocess.run", return_value=SimpleNamespace(returncode=0)) as execute:
            self.assertEqual(run_worker(run["run_id"], settings=self.settings), 0)
        prepare, simulate = execute.call_args_list
        self.assertIn("--market-snapshot", prepare.args[0])
        self.assertIn("--start-date", prepare.args[0])
        for call in (prepare, simulate):
            self.assertNotIn("TUSHARE_TOKEN", call.kwargs["env"])
            self.assertEqual(call.kwargs["env"]["TWINMARKET_MARKET_SNAPSHOT_ID"], metadata["snapshot_id"])
            self.assertTrue(call.kwargs["env"]["TWINMARKET_DATA_DIR"].endswith(metadata["snapshot_id"]))
        self.assertNotIn("--checkpoint", simulate.args[0])

    def test_api_contract_redaction_and_snapshot_activation(self):
        client = TestClient(create_app(self.settings))
        result = client.get("/api/settings/data-sources")
        self.assertEqual(result.status_code, 200)
        self.assertNotIn(SECRET, result.text)
        self.assertEqual(client.put("/api/settings/data-sources/tushare", json={"enabled": True}).status_code, 200)
        self.assertEqual(client.post("/api/market/sync-jobs", json=self.request(allow_missing_news=False)).json()["code"], "NEWS_MISSING_NOT_ALLOWED")
        with patch("backend.services.market_sync.subprocess.Popen", return_value=SimpleNamespace(pid=os.getpid())) as launch:
            response = client.post("/api/market/sync-jobs", json=self.request())
        self.assertEqual(response.status_code, 202)
        self.assertNotIn(SECRET, str(launch.call_args))
        result = self.service.execute(response.json()["job_id"], self.fake.provider())
        snapshot_id = result["snapshot_id"]
        self.assertEqual(client.get(f"/api/market/sync-jobs/{result['job_id']}").json()["status"], "completed")
        self.assertEqual(client.post(f"/api/market/snapshots/{snapshot_id}/activate").status_code, 200)
        self.assertEqual(client.get("/api/market/overview").json()["active_snapshot"]["snapshot_id"], snapshot_id)
        self.assertEqual(client.get("/api/market/snapshots/market-missing").status_code, 404)
        self.assertEqual(client.get("/api/market/snapshots").json()["items"][0]["snapshot_id"], snapshot_id)
        body = {"name": "api-run", "config": {"start_date": "2025-01-13", "end_date": "2025-01-14", "allow_missing_news": True}}
        created = client.post("/api/runs", json=body)
        self.assertEqual(created.status_code, 201, created.text)
        run_id = created.json()["run_id"]
        body["config"]["start_date"] = "2025-01-14"
        self.assertEqual(client.patch(f"/api/runs/{run_id}", json=body).status_code, 200)
        saved = json.loads((self.settings.runs_dir / run_id / "manifest.json").read_text())
        self.assertEqual(saved["parameters"]["start_date"], "2025-01-14")
        self.assertEqual(client.get(f"/api/runs/{run_id}").json()["checkpoint"]["next_date"], "2025-01-14")
        self.assertEqual(client.post(f"/api/runs/{run_id}/copy").json()["config"]["market_snapshot_id"], snapshot_id)
        # Run config becomes immutable after queueing.
        RunRegistry(self.settings.registry_path).transition(run_id, "queued")
        self.assertEqual(client.patch(f"/api/runs/{run_id}", json=body).status_code, 409)


class InputAndIndexTests(unittest.TestCase):
    def test_actual_calendar_date_not_previous_trade_date_and_empty_news(self):
        calendar = pd.DataFrame({"cal_date": ["2025-01-10", "2025-01-11"], "pretrade_date": ["2025-01-09", "2025-01-10"], "is_open": [1, 0]})
        self.assertEqual(open_trading_dates(calendar), {pd.Timestamp("2025-01-10")})
        news = pd.DataFrame({"cal_date": ["2025-01-10"], "news": [[]]})
        self.assertEqual(news_for_date(news, pd.Timestamp("2025-01-11")), [])
        self.assertEqual(EmptyNewsIndex().search_news_batch(queries=["old news"]), [[]])

    def test_harmonic_valuation_nonpositive_missing_and_coverage(self):
        constituents = [{"ts_code": "a", "weight": .8}, {"ts_code": "b", "weight": .2}]
        self.assertEqual(ratio({"a": {"pe_ttm": 10}, "b": {"pe_ttm": 20}}, constituents, "pe_ttm"), (1 / .09, 1.0))
        self.assertEqual(ratio({"a": {"pe_ttm": -1}, "b": {"pe_ttm": 20}}, constituents, "pe_ttm"), (None, .2))

    def test_suspension_returns_zero_and_ma_uses_only_prior_and_current(self):
        assets = {"TEST": {"name": "Test", "constituents": [{"ts_code": "a", "weight": .9}, {"ts_code": "b", "weight": .1}]}}
        history = pd.DataFrame([{ "ts_code": "TEST", "date": "2025-01-10", "close": 10, "pre_close": 10, "amount": 1, "vol": 100 }])
        daily = {"2025-01-13": {"a": {"close": 11, "pre_close": 10, "pct_chg": 10, "vol": 1, "amount": 1}}}
        output, warnings, coverage = build_indices(assets, history, daily, {}, ["2025-01-13"])
        self.assertAlmostEqual(output.iloc[-1]["close"], 10.9)
        self.assertAlmostEqual(output.iloc[-1]["ma_hfq_5"], 10.45)
        self.assertTrue(warnings)
        self.assertEqual(coverage[0]["weight"], .9)


class SimulationSmokeTests(MarketFixture):
    def test_one_user_two_days_fake_model_real_matching_settlement_and_results(self):
        import subprocess
        import sys
        from backend.results import results_agents
        from script.prepare_simulation_run import write_beliefs
        # Production-sized fixture schema, copied into a private database.
        template = self.settings.data_dir / 'real-template.db'
        shutil.copyfile(ROOT / 'data' / 'sys_1000.db', template)
        _, metadata = self.sync()
        _, snapshot = resolve_snapshot(self.settings, metadata['snapshot_id'], allow_missing_news=True)
        folder = self.root / 'smoke'
        folder.mkdir()
        selected = prepare_database(template, folder / 'users.db', 1, market_snapshot=snapshot, start_date='2025-01-13')
        beliefs = self.root / 'smoke-beliefs.csv'
        beliefs.write_text('user_id,belief\n' + selected[0] + ',观察市场\n')
        write_beliefs(beliefs, folder / 'belief.csv', selected)
        (folder / 'state.json').write_text(json.dumps({'status': 'draft', 'checkpoint': {}}))
        env = {**os.environ, 'TWINMARKET_DATA_DIR': str(snapshot), 'TWINMARKET_MARKET_SNAPSHOT_ID': metadata['snapshot_id'],
               'MPLCONFIGDIR': str(folder / 'matplotlib'), 'PYTHONPATH': str(ROOT)}
        result = subprocess.run([sys.executable, '-m', 'backend.tests.market_smoke_runner', str(folder)], cwd=ROOT,
                                env=env, text=True, capture_output=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout[-10000:] + result.stderr[-6000:])
        state = json.loads((folder / 'state.json').read_text())
        self.assertEqual(state['checkpoint']['last_completed_date'], '2025-01-14')
        events = [json.loads(line) for line in (folder / 'events.jsonl').read_text().splitlines()]
        failures = [item for item in events if item['event'] == 'stage_failed']
        self.assertEqual(failures, [], result.stdout[-10000:])
        observed = json.loads((folder / 'observations.json').read_text())
        self.assertEqual(observed, [{'simulation_date': '2025-01-13', 'observation_through': '2025-01-10'},
                                    {'simulation_date': '2025-01-14', 'observation_through': '2025-01-13'}])
        with sqlite3.connect(folder / 'users.db') as db:
            self.assertEqual(db.execute("SELECT count(*) FROM StockData WHERE date='2025-01-14'").fetchone()[0], 10)
            self.assertEqual(db.execute("SELECT count(*) FROM Profiles WHERE created_at='2025-01-14 00:00:00'").fetchone()[0], 1)
        transactions = folder / 'simulation_results' / '2025-01-13' / 'transactions_2025-01-13.csv'
        self.assertTrue(transactions.is_file(), result.stdout[-10000:])
        self.assertIn('stock_code', pd.read_csv(transactions).columns)
        # One user has no counterparty; submitted orders and zero fills are valid.
        self.assertTrue((folder / 'trading_records' / '2025-01-13_orders.json').is_file())
        # Use the same result service as HTTP without renaming or mutating inputs.
        shutil.copyfile(folder / 'users.db', folder / 'user_1.db')
        items = results_agents({'output_dir': str(folder), 'config': {'user_count': 1}}, 1, 50)['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['as_of'], '2025-01-14 00:00:00')
