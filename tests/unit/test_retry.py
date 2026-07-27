import pytest

from titan_x.infrastructure.retry import RetryConfig, retry_async


@pytest.mark.asyncio
async def test_retry_succeeds_on_first_attempt() -> None:
    call_count: int = 0

    async def func() -> str:
        nonlocal call_count
        call_count += 1
        return "ok"

    config = RetryConfig(max_attempts=3, base_delay=0.01)
    decorated = retry_async(config)(func)
    result = await decorated()
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_succeeds_on_retry() -> None:
    call_count: int = 0

    async def func() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("not yet")
        return "ok"

    config = RetryConfig(max_attempts=3, base_delay=0.01)
    decorated = retry_async(config)(func)
    result = await decorated()
    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_exhausts_attempts() -> None:
    call_count: int = 0

    async def func() -> str:
        nonlocal call_count
        call_count += 1
        raise ValueError("always fail")

    config = RetryConfig(max_attempts=3, base_delay=0.01)
    decorated = retry_async(config)(func)
    with pytest.raises(ValueError, match="always fail"):
        await decorated()
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_single_attempt_no_retry() -> None:
    call_count: int = 0

    async def func() -> str:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("fail")

    config = RetryConfig(max_attempts=1, base_delay=0.01)
    decorated = retry_async(config)(func)
    with pytest.raises(RuntimeError):
        await decorated()
    assert call_count == 1
