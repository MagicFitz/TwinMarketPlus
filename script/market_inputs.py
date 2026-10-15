"""Small simulation input helpers, independent of model/network initialization."""
import pandas as pd


def open_trading_dates(calendar):
    opened = calendar["is_open"].astype(str).str.lower().isin(["1", "open"])
    return set(pd.to_datetime(calendar.loc[opened, "cal_date"]).dt.normalize())


def news_for_date(news, current_date):
    selected = news[pd.to_datetime(news["cal_date"]).dt.normalize() == pd.Timestamp(current_date).normalize()]
    if selected.empty:
        return []
    result = selected.iloc[0]["news"]
    return result if isinstance(result, list) else []


class EmptyNewsIndex:
    def search_news_batch(self, *, queries, **kwargs):
        return [[] for _ in queries]
