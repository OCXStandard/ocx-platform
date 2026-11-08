"""Exception hierarchy for ocx-integrity."""

from __future__ import annotations


class IntegrityError(Exception):
    """Base class for all ocx-integrity errors."""


class InvalidKeyError(IntegrityError):
    """The yard key is missing, not hex, or shorter than 32 bytes."""


class DuplicatePartIdError(IntegrityError):
    """Two parts resolve to the same part ID (e.g. a reused GUID)."""

    def __init__(self, part_ids: list[str]) -> None:
        self.part_ids = part_ids
        super().__init__(f"duplicate part IDs: {', '.join(part_ids)}")


class ProfileMismatchError(IntegrityError):
    """A manifest/bundle uses a profile other than the one expected."""


class UnknownPartError(IntegrityError):
    """A requested part ID or aspect is not present in the manifest."""


class PartDriftError(IntegrityError):
    """The model's rebuilt part hash differs from the manifest entry."""
