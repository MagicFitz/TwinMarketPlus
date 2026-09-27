import tempfile
import unittest
from pathlib import Path

from backend.registry import ConflictError, RunRegistry
from runtime import EventStore, RuntimeObserver, RuntimeSnapshotReducer
from runtime.event import RuntimeEvent
from runtime.schemas import EventType, Scope


class RuntimeEventTests(unittest.TestCase):
    def test_store_orders_recovers_and_redacts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.jsonl"
            store = EventStore(path, buffer_size=2)
            event = store.append(RuntimeEvent(0, "run-a", EventType.STARTED, Scope.AGENT, "state", agent_id="7", input_summary={"api_key": "secret", "cash": 10}))
            self.assertEqual(event.event_id, 1)
            self.assertNotIn("secret", path.read_text())
            self.assertEqual(EventStore(path).after(0)[0].agent_id, "7")
            with self.assertRaises(ValueError):
                store.append(RuntimeEvent(1, "run-a", EventType.COMPLETED, Scope.AGENT, "state"))

    def test_reducer_ignores_duplicate_and_keeps_agent_failure_local(self):
        reducer = RuntimeSnapshotReducer("run-a")
        failure = RuntimeEvent(1, "run-a", EventType.FAILED, Scope.AGENT, "action", agent_id="42", error_code="timeout")
        reducer.apply(failure)
        reducer.apply(failure)
        state = reducer.as_dict()
        self.assertEqual(state["last_event_id"], 1)
        self.assertEqual(state["agents"][0]["stages"]["action"]["status"], "failed")
        self.assertEqual(state["run"]["status"], "pending")

    def test_observer_failure_does_not_escape(self):
        class Broken:
            def append(self, event):
                raise OSError("disk full")

        degraded = []
        self.assertIsNone(RuntimeObserver("r", Broken(), degraded.append).started(Scope.RUN, "run"))
        self.assertEqual(len(degraded), 1)


class RegistryTests(unittest.TestCase):
    def test_lifecycle_and_idempotent_transition(self):
        with tempfile.TemporaryDirectory() as folder:
            registry = RunRegistry(Path(folder) / "runs.sqlite3")
            config = {"start_date": "2023-06-15"}
            record = registry.create("r1", "name", "", config, Path(folder) / "r1")
            self.assertEqual(record["status"], "draft")
            self.assertEqual(registry.transition("r1", "queued")["status"], "queued")
            self.assertEqual(registry.transition("r1", "queued")["status"], "queued")
            with self.assertRaises(ConflictError):
                registry.transition("r1", "completed")


if __name__ == "__main__":
    unittest.main()
