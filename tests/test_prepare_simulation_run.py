import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from script.prepare_simulation_run import prepare_database, write_beliefs


class PrepareSimulationRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.template = self.root / "template.db"
        with sqlite3.connect(self.template) as connection:
            connection.execute("CREATE TABLE Profiles (user_id TEXT, created_at TEXT)")
            connection.execute("CREATE TABLE Strategy (user_id TEXT, strategy TEXT)")
            connection.execute("CREATE TABLE TradingDetails (user_id TEXT)")
            for user_id in ("3", "1", "2"):
                connection.execute("INSERT INTO Profiles VALUES (?, '2023-06-14')", (user_id,))
                connection.execute("INSERT INTO Strategy VALUES (?, 'hold')", (user_id,))
                connection.execute("INSERT INTO TradingDetails VALUES (?)", (user_id,))
        self.beliefs = self.root / "beliefs.csv"
        with self.beliefs.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["user_id", "belief"])
            writer.writeheader()
            for user_id in ("1", "2", "3"):
                writer.writerow({"user_id": user_id, "belief": "0.5"})

    def tearDown(self):
        self.temp.cleanup()

    def test_selected_ids_beliefs_and_database_integrity_match(self):
        database = self.root / "run" / "users.db"
        selected_ids = prepare_database(self.template, database, 2)
        beliefs = self.root / "run" / "beliefs.csv"
        write_beliefs(self.beliefs, beliefs, selected_ids)

        self.assertEqual(selected_ids, ["1", "2"])
        with sqlite3.connect(database) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("SELECT count(*) FROM Profiles").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT count(*) FROM Strategy").fetchone()[0], 2)
        with beliefs.open(newline="", encoding="utf-8") as handle:
            self.assertEqual([row["user_id"] for row in csv.DictReader(handle)], selected_ids)

    def test_refuses_to_overwrite_existing_outputs(self):
        database = self.root / "users.db"
        database.touch()
        with self.assertRaises(FileExistsError):
            prepare_database(self.template, database, 1)
        beliefs = self.root / "beliefs.csv"
        with self.assertRaises(FileExistsError):
            write_beliefs(self.beliefs, beliefs, ["1"])

