"""Local, read-only adapter for the existing TwinMarket files. No simulation imports."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import yaml
from contextlib import closing
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
SAFE_CONFIG = ('start_date', 'end_date', 'node', 'max_workers', 'activate_prob',
               'prob_of_technical', 'similarity_threshold', 'time_decay_factor')


def local(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError('Path is outside the workspace')
    return resolved


def rows(db: Path, sql: str, values=()) -> list[dict]:
    if db is None:
        raise FileNotFoundError('Data source is unavailable')
    path = local(db)
    if not path.is_file():
        raise FileNotFoundError('Data source is unavailable')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only = ON')
        return [dict(r) for r in conn.execute(sql, values)]


def scalar(db, sql, values=()):
    result = rows(db, sql, values)
    return next(iter(result[0].values())) if result else None


def log_data(folder):
    paths = [local(p) for p in folder.glob('simulation*.log')]
    if not paths:
        return '', '', None
    path = max(paths, key=lambda p: p.stat().st_mtime)
    with path.open('rb') as f:
        head = f.read(65536).decode('utf-8', errors='replace')
        size = f.seek(0, 2)
        f.seek(max(0, size - 131072))
        tail = f.read().decode('utf-8', errors='replace')
    return head, tail, max(0, datetime.now().timestamp() - path.stat().st_mtime)


def config_from_log(head):
    match = re.search(r'=== 模拟配置参数 ===\s*(\{.*?\})', head, re.S)
    try:
        config = json.loads(match.group(1)) if match else {}
    except ValueError:
        config = {}
    return {k: config[k] for k in SAFE_CONFIG if k in config}


def run_folders():
    return {p.name: local(p) for p in sorted(ROOT.glob('logs_*')) if p.is_dir()}


def database(folder, pattern):
    choices = sorted(folder.glob(pattern))
    return local(choices[0]) if choices else None


def count_files(folder, pattern):
    return sum(p.is_file() for p in folder.glob(pattern))


def calendar(start, end):
    if not start or not end:
        return []
    with (ROOT / 'data/trading_days.csv').open(newline='') as f:
        return [r for r in csv.DictReader(f) if start <= r['cal_date'] <= end]


def clean_log(tail):
    # Display operational lines only, never raw model responses or config contents.
    allowed = (r'=== 当前日期: \d{4}-\d{2}-\d{2} ===', r'交易日: (?:True|False)',
               r'用户关系图属性: \d+ 个节点, \d+ 条边',
               r'开始处理 \d+ 个用户，使用 \d+ 个工作线程',
               r'成功处理 \d+ 个用户', r'=== 模拟系统运行完成 ===',
               r'处理输入 \d{4}-\d{2}-\d{2}:\s*\d+%')
    output = []
    for line in tail.replace('\r', '\n').splitlines():
        line = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', line).strip()
        for pattern in allowed:
            match = re.match(pattern, line)
            if match:
                event = match.group(0)
                if not output or event != output[-1]:
                    output.append(event)
                break
    return output[-16:]


def snapshot(run_id):
    folder = run_folders()[run_id]
    db = database(folder, 'user*.db')
    forum = database(folder, 'forum*.db')
    head, tail, age = log_data(folder)
    config = config_from_log(head)
    dates = re.findall(r'=== 当前日期: (\d{4}-\d{2}-\d{2}) ===', head + tail)
    current = dates[-1] if dates else None
    start, end = config.get('start_date'), config.get('end_date')
    days = calendar(start, end)
    stats = rows(db, 'SELECT count(DISTINCT user_id) users, max(created_at) latest FROM Profiles')[0] if db else {'users': None, 'latest': None}
    latest = str(stats['latest'])[:10] if stats['latest'] else None
    snapshot_dates = {r['date'] for r in rows(db, 'SELECT DISTINCT substr(created_at,1,10) date FROM Profiles')} if db else set()
    # Profiles may be committed before forum actions; this is a snapshot watermark, not run completion.
    for day in days:
        day['snapshotted'] = day['cal_date'] in snapshot_dates
    completed = '=== 模拟系统运行完成 ===' in tail
    status = 'completed' if completed else ('stale' if age is not None and age > 120 else 'observed' if age is not None else 'unknown')
    all_trades = scalar(db, 'SELECT count(*) FROM TradingDetails') if db else None
    new_trades = scalar(db, 'SELECT count(*) FROM TradingDetails WHERE date_time >= ?', (start,)) if db and start else None
    artifacts = {k: count_files(folder / k, '**/*.json') for k in ('conversation_records', 'trading_records', 'post_records', 'reaction_records')}
    artifacts['graphs'] = count_files(folder / 'graphs', '*.pkl')
    return {
        'id': run_id, 'name': run_id.removeprefix('logs_').replace('_', ' '),
        'status': status, 'config': config, 'current_date': current,
        'snapshot_through': latest, 'log_age_seconds': age,
        'users': stats['users'], 'days': days,
        'asset_count': scalar(db, 'SELECT count(*) FROM StockProfile') if db else None,
        'trading_days_done': sum(d['snapshotted'] for d in days if d['is_open'] == 'open'),
        'trading_days_total': sum(d['is_open'] == 'open' for d in days),
        'calendar_days_done': sum(d['snapshotted'] for d in days),
        'trades': new_trades, 'historical_trades': all_trades - new_trades if all_trades is not None and new_trades is not None else None,
        'posts': scalar(forum, 'SELECT count(*) FROM posts') if forum else None,
        'reactions': scalar(forum, 'SELECT count(*) FROM reactions') if forum else None,
        'conversations_today': count_files(folder / 'conversation_records' / current, '*.json') if current else None,
        'artifacts': artifacts, 'logs': clean_log(tail),
        'observed_at': datetime.now().astimezone().isoformat(),
        'state_note': '已检测到完成标记' if completed else '仅根据日志更新时间观测，未检测模拟进程是否存活',
    }


def get_db(run_id):
    if run_id == 'template':
        return ROOT / 'data/sys_1000.db'
    return database(run_folders()[run_id], 'user*.db')


def members(run_id, query):
    db = get_db(run_id)
    search = query.get('q', [''])[0][:100]
    page = min(1000000, max(1, int(query.get('page', ['1'])[0])))
    where = 'created_at = (SELECT max(created_at) FROM Profiles) AND (user_id LIKE ? OR user_type LIKE ? OR location LIKE ?)'
    params = (f'%{search}%',) * 3
    total = scalar(db, f'SELECT count(*) FROM Profiles WHERE {where}', params)
    data = rows(db, f'''SELECT user_id, user_type, location,
        bh_disposition_effect_category disposition, bh_lottery_preference_category lottery,
        current_cash, total_value, return_rate, created_at
        FROM Profiles WHERE {where} ORDER BY user_id LIMIT 20 OFFSET ?''', (*params, (page - 1) * 20))
    return {'items': data, 'total': total, 'page': page}


def member_detail(run_id, user_id):
    result = rows(get_db(run_id), '''SELECT user_id, user_type, location, gender,
        bh_disposition_effect_category disposition, bh_lottery_preference_category lottery,
        bh_underdiversification_category diversification,
        current_cash, total_value, return_rate, cur_positions, created_at
        FROM Profiles WHERE user_id = ? ORDER BY created_at DESC LIMIT 1''', (user_id,))
    if not result:
        raise KeyError('Unknown member')
    item = result[0]
    try:
        item['positions'] = json.loads(item.pop('cur_positions') or '{}')
    except ValueError:
        item['positions'] = {}
    strategies = rows(get_db(run_id), 'SELECT strategy FROM Strategy WHERE CAST(user_id AS TEXT) = ? LIMIT 1', (user_id,))
    item['strategy'] = strategies[0]['strategy'] if strategies else None
    return item


def market(run_id, asset):
    db = get_db(run_id)
    assets = rows(db, 'SELECT stock_id, name, industry, weight, description FROM StockProfile ORDER BY weight DESC')
    chosen = asset or (assets[0]['stock_id'] if assets else '')
    prices = rows(db, '''SELECT date, close_price, pct_chg, vol FROM StockData
        WHERE stock_id = ? ORDER BY date DESC LIMIT 180''', (chosen,))[::-1]
    return {'assets': assets, 'selected': chosen, 'prices': prices,
            'source': '初始化模板历史行情' if run_id == 'template' else '实验数据库（含初始化历史）'}


def catalog():
    db = ROOT / 'data/sys_1000.db'
    users = scalar(db, 'SELECT count(DISTINCT user_id) FROM Profiles')
    distributions = rows(db, '''SELECT user_type name, count(*) value FROM Profiles
        WHERE created_at = (SELECT max(created_at) FROM Profiles) GROUP BY user_type''')
    market_range = rows(db, 'SELECT min(date) start, max(date) end, count(*) records FROM StockData')[0]
    inventory = []
    for relative, name in [('data/stock_data.csv', '行业指数行情'), ('data/trading_days.csv', '交易日历'),
                           ('data/sorted_impact_news.pkl', '每日新闻'), ('data/InformationDB_news_2023/faiss_index.pkl', '新闻向量索引')]:
        path = local(ROOT / relative)
        inventory.append({'name': name, 'path': relative, 'available': path.is_file(),
                          'bytes': path.stat().st_size if path.is_file() else None})
    connections = []
    for filename, kind, name in [('api.yaml', 'language', '语言模型'), ('embedding.yaml', 'embedding', '向量模型')]:
        path = local(ROOT / 'config' / filename)
        # Read only the model label; no credential values leave this adapter.
        model = None
        if path.is_file():
            for line in path.read_text().splitlines():
                match = re.match(r'^model_name:\s*([\w./-]+)\s*$', line)
                if match:
                    model = match.group(1)
        connections.append({'kind': kind, 'name': name, 'model': model,
                            'configured': path.is_file(), 'tested': False})
    return {'group': {'id': 'template', 'name': '基础投资者群体', 'users': users, 'distributions': distributions,
                      'source': 'data/sys_1000.db', 'status': '本地模板 · 未注册版本'},
            'market_range': market_range, 'inventory': inventory, 'connections': connections}


class FrontmatterLoader(yaml.SafeLoader):
    """Reject ambiguous duplicate keys, including conflicting publication flags."""
    def construct_mapping(self, node, deep=False):
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if any(not isinstance(key, str) for key in keys) or len(keys) != len(set(keys)):
            raise ValueError('Invalid frontmatter keys')
        return super().construct_mapping(node, deep=deep)


def published_documents():
    root = local(ROOT / 'docs')
    result = []
    if not root.is_dir():
        return result
    for candidate in sorted(root.rglob('*.md')):
        try:
            path = candidate.resolve()
            if not path.is_relative_to(root) or path.is_symlink() or candidate.is_symlink():
                continue
            if not path.is_file() or path.stat().st_size > 1024 * 1024:
                continue
            source = path.read_text(encoding='utf-8-sig')
            match = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)', source, re.S)
            if not match or len(match.group(1)) > 16384:
                continue
            metadata = yaml.load(match.group(1), Loader=FrontmatterLoader)
            if not isinstance(metadata, dict) or metadata.get('published') is not True:
                continue
            body = source[match.end():].lstrip('\r\n')
            heading = re.search(r'^#\s+(.+)$', body, re.M)
            title = metadata.get('title', heading.group(1) if heading else path.stem)
            category = metadata.get('category', '文档')
            order = metadata.get('order', 100)
            if not isinstance(title, str) or not isinstance(category, str):
                continue
            if type(order) is not int:
                order = 100
            result.append({'path': path.relative_to(root).as_posix(), 'title': title[:160],
                           'category': category[:80], 'order': order, 'content': body})
        except (OSError, ValueError, yaml.YAMLError, RecursionError):
            # Malformed or unreadable files remain private; never fail open.
            continue
    return sorted(result, key=lambda item: (item['order'], item['title'], item['path']))


def documentation(query):
    documents = published_documents()  # Recheck publication on every list/detail request.
    requested = query.get('path', [None])[0]
    if requested is not None:
        for document in documents:
            if document['path'] == requested:
                return document
        raise KeyError('Unpublished or unknown document')
    return {'items': [{k: v for k, v in doc.items() if k != 'content'} for doc in documents]}


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        parts = parsed.path.strip('/').split('/')
        try:
            if parsed.path == '/api/runs':
                data = []
                for run_id in run_folders():
                    try:
                        data.append(snapshot(run_id))
                    except (sqlite3.Error, OSError, ValueError):
                        data.append({'id': run_id, 'name': run_id, 'status': 'unavailable', 'users': None})
                data.sort(key=lambda r: (r.get('current_date') or '', r['id']), reverse=True)
                result = {'items': data, 'observed_at': datetime.now().astimezone().isoformat()}
            elif parsed.path == '/api/catalog':
                result = catalog()
            elif parsed.path == '/api/documentation':
                result = documentation(query)
            elif len(parts) >= 4 and parts[:2] == ['api', 'runs']:
                run_id, resource = parts[2:4]
                if resource == 'snapshot' and len(parts) == 4:
                    result = snapshot(run_id)
                elif resource == 'agents' and len(parts) == 4:
                    result = members(run_id, query)
                elif resource == 'agents' and len(parts) == 5:
                    result = member_detail(run_id, parts[4])
                elif resource == 'market' and len(parts) == 4:
                    result = market(run_id, query.get('asset', [None])[0])
                else:
                    raise KeyError('Unknown endpoint')
            else:
                raise KeyError('Unknown endpoint')
            self.reply(200, result)
        except KeyError:
            self.reply(404, {'error': '找不到该资源'})
        except (ValueError, OSError, sqlite3.Error):
            self.reply(503, {'error': '数据暂不可用，请稍后刷新；现有数据已保留'})

    def do_POST(self):
        self.reply(405, {'error': '此原型仅支持只读访问'})

    do_PUT = do_PATCH = do_DELETE = do_POST


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    print(f'TwinMarket read-only API on 127.0.0.1:{args.port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
