"""Fixed listing diagnostics; catalog and validation details stay private."""

from enum import StrEnum
from types import MappingProxyType


class ListingCode(StrEnum):
    """Safe failures for metadata discovery, independent of evaluation errors."""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    POLICY_ASSETS_INVALID = "POLICY_ASSETS_INVALID"
    POLICY_LIST_LIMIT_EXCEEDED = "POLICY_LIST_LIMIT_EXCEEDED"
    SERVER_BUSY = "SERVER_BUSY"
    INTERNAL_ERROR = "INTERNAL_ERROR"


LISTING_MESSAGES = MappingProxyType(
    {
        ListingCode.INVALID_ARGUMENT: "Invalid policy listing arguments.",
        ListingCode.POLICY_ASSETS_INVALID: "The packaged policy assets are invalid.",
        ListingCode.POLICY_LIST_LIMIT_EXCEEDED: "The policy list exceeds its limit.",
        ListingCode.SERVER_BUSY: "Another policy listing is already running.",
        ListingCode.INTERNAL_ERROR: "The policy list could not be completed.",
    }
)


class ListingFailure(Exception):
    """Carry only a known code and fixed prose across the application boundary."""

    def __init__(self, code: ListingCode) -> None:
        if not isinstance(code, ListingCode):
            raise TypeError("Listing failures require a known code.")
        self.code = code
        super().__init__(f"{code.value}: {LISTING_MESSAGES[code]}")
