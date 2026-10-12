"""Versioned definitions retain the ten historical TwinMarket baskets."""
import hashlib
import math
import re
from datetime import date

import yaml

from .errors import MarketError

ASSET_CODES = {"TLEI", "MEI", "CPEI", "IEEI", "REEI", "TSEI", "CGEI", "TTEI", "EREI", "FSEI"}


def load_assets(path):
    raw = path.read_bytes()
    document = yaml.safe_load(raw)
    assets = document.get("assets", {})
    if document.get("schema_version") != 1 or set(assets) != ASSET_CODES:
        raise MarketError("ASSET_DEFINITION_INVALID", "资产定义必须包含现有 10 个指数")
    date.fromisoformat(document["effective_from"])
    all_codes = []
    for code, asset in assets.items():
        weights = [row["weight"] for row in asset["constituents"]]
        if not weights or any(not isinstance(w, (int, float)) or not math.isfinite(w) or w <= 0 for w in weights):
            raise MarketError("ASSET_DEFINITION_INVALID", f"{code} 成分权重无效")
        if not math.isclose(sum(weights), 1, abs_tol=1e-6):
            raise MarketError("ASSET_DEFINITION_INVALID", f"{code} 权重合计必须为 1")
        codes = [row["ts_code"] for row in asset["constituents"]]
        if len(codes) != len(set(codes)) or any(not re.fullmatch(r"\d{6}\.(SH|SZ)", c) for c in codes):
            raise MarketError("ASSET_DEFINITION_INVALID", f"{code} 成分代码无效")
        all_codes.extend(codes)
    if len(set(all_codes)) != 50:
        raise MarketError("ASSET_DEFINITION_INVALID", "资产定义必须包含 50 只独立成分股")
    return document, hashlib.sha256(raw).hexdigest()
