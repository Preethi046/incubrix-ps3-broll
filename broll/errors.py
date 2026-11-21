class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, retryable: bool = False, details: dict | None = None):
        self.code, self.message, self.status = code, message, status
        self.retryable, self.details = retryable, details or {}
        super().__init__(message)
    def body(self):
        return {"error": {"code": self.code, "message": self.message, "retryable": self.retryable, "details": self.details}}
