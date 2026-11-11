from __future__ import annotations


class Slap2VoltageError(ValueError):
    """Domain error carrying a stable machine-readable identifier."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")
