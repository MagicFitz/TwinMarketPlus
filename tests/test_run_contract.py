import unittest
import tempfile
from pathlib import Path

from script.run_contract import clear_date_scoped_artifacts, run_dir_for


class RunContractTests(unittest.TestCase):
    def test_run_id_must_be_a_single_safe_directory_name(self):
        self.assertEqual(run_dir_for("run_001").name, "run_001")
        with self.assertRaises(ValueError):
            run_dir_for("../escape")

    def test_checkpoint_cleanup_keeps_earlier_artifacts_and_removes_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = root / "trading_records" / "2023-06-15.json"
            boundary = root / "trading_records" / "2023-06-16.json"
            nested = root / "conversation_records" / "2023-06-16" / "user.json"
            graph_before = root / "graphs" / "user_graph_2023-06-15.pkl"
            graph_boundary = root / "graphs" / "user_graph_2023-06-16.pkl"
            for artifact in (before, boundary, nested, graph_before, graph_boundary):
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_text("artifact", encoding="utf-8")

            clear_date_scoped_artifacts(root, "2023-06-16")

            self.assertTrue(before.exists())
            self.assertTrue(graph_before.exists())
            self.assertFalse(boundary.exists())
            self.assertFalse(nested.parent.exists())
            self.assertFalse(graph_boundary.exists())
