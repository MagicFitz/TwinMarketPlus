"""Deterministic fixed-weight, chain-linked baskets, with explicit missingness."""
import math

import pandas as pd

from .errors import MarketError

TRANSFORM_VERSION = "twin-index-v1"


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def ratio(rows, constituents, field):
    valid = [(c["weight"], number(rows.get(c["ts_code"], {}).get(field))) for c in constituents]
    valid = [(w, v) for w, v in valid if v is not None and v > 0]
    coverage = sum(w for w, _ in valid)
    return (1 / sum(w / v for w, v in valid) if coverage >= .8 else None), coverage


def build_indices(assets, history, daily, basics, trading_dates):
    warnings, coverage_report, generated = [], [], []
    histories = {code: history[history.ts_code == code].sort_values("date") for code in assets}
    for code, frame in histories.items():
        if frame.empty or number(frame.iloc[-1]["close"]) is None or float(frame.iloc[-1]["close"]) <= 0:
            raise MarketError("DATA_BRIDGE_MISSING", f"{code} 缺少桥接历史收盘价")
    last_prices = {code: float(frame.iloc[-1]["close"]) for code, frame in histories.items()}
    for day in trading_dates:
        rows, indicators = daily.get(day, {}), basics.get(day, {})
        for code, asset in assets.items():
            constituents = asset["constituents"]
            valid = []
            for c in constituents:
                row = rows.get(c["ts_code"])
                if not row:
                    continue  # Missing constituents contribute zero return, without renormalization.
                close, previous, volume, amount = (number(row.get(k)) for k in ("close", "pre_close", "vol", "amount"))
                if any(v is None for v in (close, previous, volume, amount)) or close <= 0 or previous <= 0 or volume < 0 or amount < 0:
                    raise MarketError("SNAPSHOT_VALIDATION_FAILED", f"{day} {c['ts_code']} 行情数值无效")
                change = close / previous - 1
                quoted = number(row.get("pct_chg"))
                if quoted is None or abs(change * 100 - quoted) > .02:
                    raise MarketError("SNAPSHOT_VALIDATION_FAILED", f"{day} 成分股涨跌幅与价格不一致")
                valid.append((c, row, change))
            coverage = sum(c["weight"] for c, _, _ in valid)
            coverage_report.append({"date": day, "ts_code": code, "weight": coverage})
            if coverage < .8 - 1e-9:
                raise MarketError("DATA_COVERAGE_INCOMPLETE", f"{day} {code} 有效成分权重低于 80%")
            if coverage < .95:
                warnings.append(f"{day} {code} 有效成分权重 {coverage:.2%}，缺失成分按停牌处理")
            r = sum(c["weight"] * change for c, _, change in valid)
            previous = last_prices[code]
            close = previous * (1 + r)
            if close <= 0:
                raise MarketError("SNAPSHOT_VALIDATION_FAILED", f"{day} {code} 指数点位无效")
            if abs(r) > .2:
                warnings.append(f"{day} {code} 涨跌幅超过 20%")
            result = {"ts_code": code, "date": day, "name": asset["name"],
                "Industry": asset["name"].removesuffix("指数"), "category": asset["name"].removesuffix("指数"),
                "close": close, "pre_close": previous, "change": close - previous, "pct_chg": r * 100,
                "vol": sum(float(row["vol"]) * 100 for _, row, _ in valid),  # hands -> shares
                "amount": sum(float(row["amount"]) * 1000 for _, row, _ in valid),  # thousand CNY -> CNY
                "elg_amount_net": None}
            for field in ("pe_ttm", "pb", "ps_ttm"):
                result[field], result[field + "_coverage"] = ratio(indicators, constituents, field)
            dividend = [(c["weight"], number(indicators.get(c["ts_code"], {}).get("dv_ttm"))) for c in constituents]
            result["dv_ttm_coverage"] = sum(w for w, v in dividend if v is not None and v >= 0)
            result["dv_ttm"] = sum(w * v for w, v in dividend if v is not None and v >= 0) if result["dv_ttm_coverage"] >= .8 else None
            generated.append(result)
            last_prices[code] = close
    output = pd.concat([history, pd.DataFrame(generated)], ignore_index=True).sort_values(["ts_code", "date"])
    # Legacy files contain amount rather than volume. Keep those legacy values as-is,
    # while every newly sourced volume is explicitly in shares.
    if "vol" not in output:
        output["vol"] = None
    for code in assets:
        mask = output.ts_code == code
        for window in (5, 10, 30):
            output.loc[mask, f"ma_hfq_{window}"] = output.loc[mask, "close"].rolling(window, min_periods=1).mean()
            output.loc[mask, f"vol_{window}"] = output.loc[mask, "vol"].rolling(window, min_periods=1).mean()
            output.loc[mask, f"ma_amount_{window}"] = output.loc[mask, "amount"].rolling(window, min_periods=1).mean()
    return output, warnings, coverage_report
