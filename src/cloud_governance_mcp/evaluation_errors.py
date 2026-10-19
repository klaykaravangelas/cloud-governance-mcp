"""Fixed evaluation diagnostics, separate from existing analysis error messages."""

from enum import StrEnum
from types import MappingProxyType


class EvaluationCode(StrEnum):
    """Execution failures are never compliance violations."""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    INVALID_POLICY_SELECTION = "INVALID_POLICY_SELECTION"
    OPA_NOT_CONFIGURED = "OPA_NOT_CONFIGURED"
    OPA_NOT_FOUND = "OPA_NOT_FOUND"
    OPA_VERSION_UNSUPPORTED = "OPA_VERSION_UNSUPPORTED"
    POLICY_ASSETS_INVALID = "POLICY_ASSETS_INVALID"
    OPA_INPUT_LIMIT_EXCEEDED = "OPA_INPUT_LIMIT_EXCEEDED"
    OPA_TIMEOUT = "OPA_TIMEOUT"
    OPA_OUTPUT_LIMIT_EXCEEDED = "OPA_OUTPUT_LIMIT_EXCEEDED"
    OPA_EXECUTION_ERROR = "OPA_EXECUTION_ERROR"
    OPA_OUTPUT_INVALID = "OPA_OUTPUT_INVALID"
    EVALUATION_LIMIT_EXCEEDED = "EVALUATION_LIMIT_EXCEEDED"
    SERVER_BUSY = "SERVER_BUSY"
    INTERNAL_ERROR = "INTERNAL_ERROR"


EVALUATION_MESSAGES = MappingProxyType(
    {
        EvaluationCode.INVALID_ARGUMENT: "Invalid evaluation arguments.",
        EvaluationCode.INVALID_POLICY_SELECTION: "Invalid policy selection.",
        EvaluationCode.OPA_NOT_CONFIGURED: "OPA is not configured.",
        EvaluationCode.OPA_NOT_FOUND: "The configured OPA executable is unavailable.",
        EvaluationCode.OPA_VERSION_UNSUPPORTED: "The OPA runtime version is unsupported.",
        EvaluationCode.POLICY_ASSETS_INVALID: "The packaged policy assets are invalid.",
        EvaluationCode.OPA_INPUT_LIMIT_EXCEEDED: "The policy input exceeds its limit.",
        EvaluationCode.OPA_TIMEOUT: "OPA exceeded its execution budget.",
        EvaluationCode.OPA_OUTPUT_LIMIT_EXCEEDED: "OPA output exceeds its limit.",
        EvaluationCode.OPA_EXECUTION_ERROR: "OPA execution failed.",
        EvaluationCode.OPA_OUTPUT_INVALID: "OPA returned an invalid policy result.",
        EvaluationCode.EVALUATION_LIMIT_EXCEEDED: "The evaluation report exceeds its limit.",
        EvaluationCode.SERVER_BUSY: "Another evaluation is already running.",
        EvaluationCode.INTERNAL_ERROR: "The evaluation could not be completed.",
    }
)


class EvaluationFailure(Exception):
    """Carry only a catalog code across workers, never subprocess/validation data."""

    def __init__(self, code: EvaluationCode) -> None:
        if not isinstance(code, EvaluationCode):
            raise TypeError("Evaluation failures require a known code.")
        self.code = code
        super().__init__(f"{code.value}: {EVALUATION_MESSAGES[code]}")
