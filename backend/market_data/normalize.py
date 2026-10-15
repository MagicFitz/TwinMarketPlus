"""Canonical constituent audit rows; supplier units never masquerade as output units."""
from datetime import datetime

from .errors import MarketError
from .indices import number


def normalize_constituents(rows):
    output = []
    for row in rows:
        try:
            day = datetime.strptime(str(row['trade_date']), '%Y%m%d').date().isoformat()
        except ValueError:
            raise MarketError('TUSHARE_INVALID_RESPONSE', '供应商日期格式无效') from None
        result = {'ts_code': row['ts_code'], 'date': day}
        for key in ('close', 'pre_close', 'pct_chg', 'vol', 'amount'):
            result[key] = number(row[key])
            if result[key] is None:
                raise MarketError('SNAPSHOT_VALIDATION_FAILED', '成分股含无效数值')
        result['vol'] *= 100
        result['amount'] *= 1000
        output.append(result)
    return output
