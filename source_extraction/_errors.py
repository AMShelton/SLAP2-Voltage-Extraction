from __future__ import annotations


class Slap2VoltageError(ValueError):
    """Domain error carrying the stable identifier used by the MATLAB implementation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")
