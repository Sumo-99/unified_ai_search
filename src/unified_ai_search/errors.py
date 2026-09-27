class SearchSDKError(Exception):
    """Base exception for all SDK failures."""


class MissingAPIKeyError(SearchSDKError):
    pass


class InvalidRequestError(SearchSDKError):
    pass


class AuthenticationError(SearchSDKError):
    pass


class RateLimitError(SearchSDKError):
    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderAPIError(SearchSDKError):
    def __init__(
        self, message: str, *, status_code: int | None = None, body: object = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class ProviderTimeoutError(SearchSDKError):
    pass


class UnsupportedOperationError(SearchSDKError):
    pass
