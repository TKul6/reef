class ReefServiceError(Exception):
    """Raised when a request cannot be served; carries the HTTP status to return to the caller."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
