"""Provider usage metadata normalization tests."""

from __future__ import annotations

from langchain_core.messages import AIMessage as LCAIMessage

from multiscribe_agent.llm.provider import from_lc_message


def test_from_lc_message_reads_model_name_from_response_metadata() -> None:
    """OpenAI-style response metadata is preserved with normalized usage."""
    response = from_lc_message(
        LCAIMessage(
            content="done",
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            response_metadata={"model_name": "gpt-4o-2024-08-06"},
        )
    )

    assert response.usage is not None
    assert response.usage.model_name == "gpt-4o-2024-08-06"


def test_from_lc_message_supports_anthropic_model_metadata_key() -> None:
    """Anthropic-style ``model`` metadata is normalized to model_name."""
    response = from_lc_message(
        LCAIMessage(
            content="done",
            usage_metadata={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
            response_metadata={"model": "claude-sonnet-4-5"},
        )
    )

    assert response.usage is not None
    assert response.usage.model_name == "claude-sonnet-4-5"


def test_from_lc_message_uses_empty_model_name_when_provider_omits_it() -> None:
    """Missing model metadata remains observable as the unknown-model bucket."""
    response = from_lc_message(
        LCAIMessage(
            content="done",
            usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        )
    )

    assert response.usage is not None
    assert response.usage.model_name == ""
