"""Validation result record (RESEARCH_CONTRACT.md §14)."""

from dataclasses import dataclass, field

from validator.errors import ErrorCode, ValidationError
from validator.hashing import VALIDATOR_VERSION


@dataclass(frozen=True, slots=True)
class ValidationResult:
    accepted: bool
    errors: tuple[ValidationError, ...]
    graph_hash: str
    scene_hash: str
    validator_version: str = field(default=VALIDATOR_VERSION)

    @property
    def error_codes(self) -> list[ErrorCode]:
        return sorted({e.code for e in self.errors})

    def __bool__(self) -> bool:
        return self.accepted
