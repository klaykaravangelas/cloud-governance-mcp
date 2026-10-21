"""Shared strict validation policy; no transport, file or provider dependencies."""

from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    """Reject coercion/extras and recheck mutable models at every boundary.

    Input hiding is defense in depth, not a public error sanitizer. Callers must
    still replace validation failures with fixed application diagnostics.
    """

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        hide_input_in_errors=True,
        validate_default=True,
        revalidate_instances="always",
    )
