import hashlib

import pytest

from multiscribe_agent.infra.db import init_db
from multiscribe_agent.services.interop import InteropError, InteropService, hash_api_key


@pytest.mark.asyncio
async def test_key_is_hashed_and_verified(tmp_path) -> None:
    database = await init_db(str(tmp_path / "interop.sqlite"))
    service = InteropService(database)
    issued = await service.generate_key("test")
    assert issued.api_key.startswith("sk_")
    row = await database.fetchone(
        "SELECT key_hash FROM interop_keys WHERE key_id = ?", (issued.key_id,)
    )
    assert row is not None
    assert row["key_hash"] == hashlib.sha256(issued.api_key.encode()).hexdigest()
    assert (await service.verify_key(issued.api_key)).key_id == issued.key_id
    await database.close()


@pytest.mark.asyncio
async def test_pending_key_requires_approval(tmp_path) -> None:
    database = await init_db(str(tmp_path / "interop.sqlite"))
    service = InteropService(database)
    issued = await service.generate_key("test", mode="approval")
    with pytest.raises(InteropError, match="not yet approved"):
        await service.verify_key(issued.api_key)
    assert await service.approve_key(issued.key_id)
    assert (await service.verify_key(issued.api_key)).approved
    await database.close()


def test_hash_helper_is_stable() -> None:
    assert hash_api_key("sk_test") == hashlib.sha256(b"sk_test").hexdigest()
