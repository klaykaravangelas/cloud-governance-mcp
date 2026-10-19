"""Operator settings shape; files.py enforces secure directory access."""

from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, ValidationError, model_validator

from cloud_governance_mcp.errors import ConfigurationError
from cloud_governance_mcp.models import ContractModel, PlanPath, PositiveInt


class AnalysisSettings(ContractModel):
    """Operator-selected roots and budgets for a single plan analysis.

    Root order matters: relative tool paths will use the first root. These
    settings validate syntax only; RestrictedPlanLoader verifies and opens roots.
    """

    # Require explicit roots; repr=False keeps their paths out of debug displays.
    allowed_roots: Annotated[list[PlanPath], Field(min_length=1, repr=False)]
    # Budgets bound input size, parser nesting, inventory size, and response size.
    max_plan_bytes: PositiveInt = 10_485_760  # 10 MiB of input bytes.
    max_json_depth: PositiveInt = 128
    max_resources: PositiveInt = 10_000
    max_analysis_bytes: PositiveInt = 4_194_304  # 4 MiB of encoded analysis JSON.

    @model_validator(mode="after")
    def absolute_roots(self) -> Self:
        """Reject roots whose meaning would depend on the working directory."""
        if not all(Path(root).is_absolute() for root in self.allowed_roots):
            raise ValueError("Allowed roots must be absolute directories.")
        return self


def validate_analysis_settings(value: object) -> AnalysisSettings:
    """Convert internal validation errors to a fixed startup diagnostic."""
    try:
        return AnalysisSettings.model_validate(value)
    except ValidationError:
        # Suppress exception chaining so startup diagnostics cannot echo paths.
        raise ConfigurationError() from None


class EvaluationSettings(ContractModel):
    """Operator-only evaluator budgets; construction never probes the binary."""

    opa_path: PlanPath | None = Field(default=None, repr=False)
    max_opa_input_bytes: PositiveInt = 4_194_304
    max_opa_output_bytes: PositiveInt = 2_097_152
    max_opa_stderr_bytes: PositiveInt = 65_536
    opa_eval_timeout_seconds: PositiveInt = 5
    opa_process_timeout_seconds: PositiveInt = 10
    max_evaluation_bytes: PositiveInt = 4_194_304

    @model_validator(mode="after")
    def absolute_executable_and_deadlines(self) -> Self:
        """A shorter process budget would defeat OPA's own evaluation timeout."""
        if self.opa_path is not None and not Path(self.opa_path).is_absolute():
            raise ValueError("Executable must be absolute.")
        if self.opa_process_timeout_seconds <= self.opa_eval_timeout_seconds:
            raise ValueError("Process deadline must exceed evaluation timeout.")
        return self


def validate_evaluation_settings(value: object) -> EvaluationSettings:
    """Keep operator paths and rejected option values out of startup errors."""
    try:
        return EvaluationSettings.model_validate(value)
    except ValidationError:
        raise ConfigurationError() from None
