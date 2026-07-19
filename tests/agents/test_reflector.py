import pytest
from conftest import FakeProvider

from multiscribe_agent.agents.reflector import Reflector
from multiscribe_agent.domain.models import AIResponse


@pytest.mark.asyncio
async def test_reflector_accepts_zero_to_ten_score() -> None:
    provider = FakeProvider(
        generated_responses=[
            AIResponse(content='{"quality":"pass","score":8.5,"feedback":"solid"}')
        ]
    )
    reflection = await Reflector().assess("Write", "Draft", provider)
    assert reflection.score == 8.5
    assert reflection.should_retry is False


@pytest.mark.asyncio
async def test_reflector_rejects_score_above_ten() -> None:
    provider = FakeProvider(
        generated_responses=[
            AIResponse(content='{"quality":"pass","score":10.5,"feedback":"too high"}')
        ]
    )
    with pytest.raises(ValueError, match="between 0 and 10"):
        await Reflector().assess("Write", "Draft", provider)
