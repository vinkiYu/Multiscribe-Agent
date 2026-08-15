"""Validate fixture labels through the Pydantic dataset contract (no re-invention)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypedDict, cast

from multiscribe_agent.eval.curation_dataset import CurationSample


class FixturePayload(TypedDict):
    """Minimal fixture shape needed for validation."""

    id: str
    candidates: list[dict[str, str]]
    expected_selected_ids: list[str]
    expected_rejected_ids: list[str]


class SchemaValidator:
    """Wrap ``CurationSample.validate_labels`` for raw fixture dictionaries."""

    def validate(self, payload: FixturePayload) -> CurationSample:
        """Build the Pydantic sample and run its label validation.

        Raises:
            pydantic.ValidationError: When the fixture does not match the schema.
            ValueError: When labels are contradictory or reference unknown ids.
        """
        sample = CurationSample.model_validate(payload)
        # The pydantic mypy plugin mis-types direct calls to validate_* methods
        # as descriptor proxies, so route through an explicit callable type.
        validator = cast(
            "Callable[[CurationSample], CurationSample]",
            CurationSample.validate_labels,
        )
        return validator(sample)


__all__ = ["SchemaValidator"]
