"""Offline child-process smoke runner; never used by production workers."""
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import yaml

from Agent import BaseAgent

calls = []


def fake_model(self, messages=None, prompt=None, **kwargs):
    prompt = messages[-1]['content'] if messages else str(prompt or kwargs.get('user_input', ''))
    calls.append(prompt)
    if 'selected_index:' in prompt:
        selected = re.findall(r'指数代码[：:]\s*(\w+)', prompt)
        result = {'selected_index': selected[:1], 'reason': 'offline snapshot smoke'}
    elif 'trading_position:' in prompt:
        matched = re.search(r'### (\w+)：.*?昨日收盘价：([\d.]+)', prompt, re.S)
        result = {matched[1]: {'action': 'buy', 'trading_position': 1, 'target_price': float(matched[2])}} if matched else {}
    elif 'queries:' in prompt:
        result = {'queries': ['运输行业']}
    elif 'post:' in prompt:
        result = {'post': '离线测试：使用已冻结的日级行情。', 'type': 'type1', 'belief': '观察市场'}
    elif 'post_id' in prompt or 'comments:' in prompt:
        result = {}
    else:
        return {'response': '{}'}
    return {'response': yaml.safe_dump(result, allow_unicode=True)}


def main():
    # The parent supplies an isolated private database and snapshot environment.
    folder, snapshot = Path(sys.argv[1]), Path(os.environ['TWINMARKET_DATA_DIR'])
    import simulation
    from util.ForumDB import init_db_forum
    original = simulation.process_user_input
    observed = []
    def observe(*args, **kwargs):
        frame, current = args[3], args[4]
        assert frame['date'].max() < current
        observed.append({'simulation_date': current.strftime('%Y-%m-%d'), 'observation_through': frame['date'].max().strftime('%Y-%m-%d')})
        return original(*args, **kwargs)
    init_db_forum(str(folder / 'forum.db'))
    with patch.object(BaseAgent, '__init__', lambda self, *args, **kwargs: None), patch.object(BaseAgent, 'get_response', fake_model), patch.object(simulation, 'process_user_input', observe):
        simulation.init_simulation(start_date=pd.Timestamp('2025-01-13'), end_date=pd.Timestamp('2025-01-14'),
            forum_db=str(folder / 'forum.db'), user_db=str(folder / 'users.db'), debug=False,
            max_workers=1, user_graph_save_name='smoke', checkpoint=False, similarity_threshold=.2,
            time_decay_factor=.5, node=1, log_dir=str(folder), prob_of_technical=0,
            belief_init_path=str(folder / 'belief.csv'), config_path='unused-offline-model', activate_prob=1,
            checkpoint_state_path=str(folder / 'state.json'), runtime_events_path=str(folder / 'events.jsonl'), run_id='smoke')
    assert len(calls) > 0, 'fake model was never called'
    (folder / 'observations.json').write_text(json.dumps(observed))
    print(json.dumps({'model_calls': len(calls), 'observations': observed, 'snapshot': snapshot.name}))


if __name__ == '__main__':
    main()
