import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class ReadOnlyTests(unittest.TestCase):
    def test_read_only_connection_blocks_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.db'
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE sample(value INTEGER)')
                conn.execute('INSERT INTO sample VALUES (7)')
            with patch.object(server,'ROOT',Path(folder).resolve()):
                self.assertEqual(server.scalar(path,'SELECT value FROM sample'),7)
                with self.assertRaises(sqlite3.OperationalError):
                    server.rows(path,'DELETE FROM sample')
                self.assertEqual(server.scalar(path,'SELECT count(*) FROM sample'),1)

    def test_path_escape_is_rejected(self):
        with self.assertRaises(ValueError):
            server.local(server.ROOT/'../../etc/passwd')

    def test_missing_database_is_not_zero(self):
        with self.assertRaises(FileNotFoundError):
            server.rows(None,'SELECT 1')

    def test_config_allowlist(self):
        config=server.config_from_log('=== 模拟配置参数 ===\n'+json.dumps({'start_date':'2023-06-15','api_key':'SECRET','base_url':'private','node':10}))
        self.assertEqual(config,{'start_date':'2023-06-15','node':10})

    def test_logs_drop_model_text_and_concatenated_http_details(self):
        lines=server.clean_log('model response SECRET\n处理输入 2023-06-21: 13%|text| HTTP Request: token SECRET\n=== 当前日期: 2023-06-21 === secret\n交易日: True\n')
        self.assertEqual(lines,['处理输入 2023-06-21: 13%','=== 当前日期: 2023-06-21 ===','交易日: True'])
        self.assertNotIn('SECRET',json.dumps(lines))

    def test_unknown_resource_not_arbitrary_path(self):
        with self.assertRaises(KeyError):
            server.get_db('../../etc/passwd')

    def test_snapshot_watermark_is_not_completion_or_contiguous_days(self):
        folder=server.ROOT/'logs_fixture'
        def fake_rows(db,sql,*args):
            if 'count(DISTINCT user_id)' in sql:
                return [{'users':10,'latest':'2023-06-20 00:00:00'}]
            return [{'date':'2023-06-20'}]
        with patch.object(server,'run_folders',return_value={'fixture':folder}), \
             patch.object(server,'database',return_value=folder/'test.db'), \
             patch.object(server,'log_data',return_value=('','=== 当前日期: 2023-06-21 ===',300)), \
             patch.object(server,'config_from_log',return_value={'start_date':'2023-06-15','end_date':'2023-06-30'}), \
             patch.object(server,'rows',side_effect=fake_rows), \
             patch.object(server,'scalar',return_value=0), \
             patch.object(server,'calendar',return_value=[{'cal_date':'2023-06-19','is_open':'open'},{'cal_date':'2023-06-20','is_open':'open'}]), \
             patch.object(server,'count_files',return_value=0):
            result=server.snapshot('fixture')
        self.assertEqual(result['status'],'stale')
        self.assertEqual(result['trading_days_done'],1)
        self.assertFalse(result['days'][0]['snapshotted'])

if __name__=='__main__':
    unittest.main()
