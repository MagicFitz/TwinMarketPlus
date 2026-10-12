class MarketError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422):
        self.code, self.status = code, status
        super().__init__(message)


class Cancelled(Exception):
    pass
