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
