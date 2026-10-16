"""Application-controlled failures; never store rejected input in public errors."""

from enum import StrEnum
from types import MappingProxyType


class ErrorCode(StrEnum):
    """Machine-readable failure reasons shared by the core and MCP layer."""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PATH_NOT_ALLOWED = "PATH_NOT_ALLOWED"
    PLAN_FILE_UNAVAILABLE = "PLAN_FILE_UNAVAILABLE"
    PLAN_LIMIT_EXCEEDED = "PLAN_LIMIT_EXCEEDED"
    INVALID_JSON = "INVALID_JSON"
    INVALID_PLAN = "INVALID_PLAN"
    UNSUPPORTED_PLAN_VERSION = "UNSUPPORTED_PLAN_VERSION"
    UNSUPPORTED_PLAN_FEATURE = "UNSUPPORTED_PLAN_FEATURE"
    ANALYSIS_LIMIT_EXCEEDED = "ANALYSIS_LIMIT_EXCEEDED"
    SERVER_BUSY = "SERVER_BUSY"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Keep explanations fixed and read-only. Building messages from rejected input
# could expose file paths, Terraform values, or malformed argument contents.
ERROR_MESSAGES = MappingProxyType(
    {
        ErrorCode.INVALID_ARGUMENT: "Invalid analysis arguments.",
        ErrorCode.PATH_NOT_ALLOWED: "The requested path is not allowed.",
        ErrorCode.PLAN_FILE_UNAVAILABLE: "The plan file is unavailable.",
        ErrorCode.PLAN_LIMIT_EXCEEDED: "The plan exceeds an input limit.",
        ErrorCode.INVALID_JSON: "The plan file is not valid UTF-8 JSON.",
        ErrorCode.INVALID_PLAN: "The document is not a valid supported Terraform plan.",
        ErrorCode.UNSUPPORTED_PLAN_VERSION: "The plan format version is unsupported.",
        ErrorCode.UNSUPPORTED_PLAN_FEATURE: "The plan contains an unsupported feature.",
        ErrorCode.ANALYSIS_LIMIT_EXCEEDED: "The analysis exceeds the output limit.",
        ErrorCode.SERVER_BUSY: "Another analysis is already running.",
        ErrorCode.INTERNAL_ERROR: "The analysis could not be completed.",
    }
)


class AnalysisError(Exception):
    """A stable code and fixed explanation suitable for the MCP boundary."""

    def __init__(self, code: ErrorCode) -> None:
        # Accept only catalog members; callers cannot supply arbitrary error text.
        if not isinstance(code, ErrorCode):
            raise TypeError("Analysis errors require a known error code.")
        self.code = code
        super().__init__(f"{code.value}: {ERROR_MESSAGES[code]}")


class ConfigurationError(Exception):
    """A startup configuration failure with no operator paths or values."""

    def __init__(self) -> None:
        super().__init__("Invalid analysis configuration.")


class UnsupportedPlatformError(Exception):
    """Startup cannot provide the filesystem guarantees required by the spec."""

    def __init__(self) -> None:
        super().__init__("Secure file loading is unsupported on this platform.")
