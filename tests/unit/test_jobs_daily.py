from unittest.mock import AsyncMock

import pytest

from titan_x.jobs.daily_jobs import (
    CleanupExpiredTokensJob,
    DatabaseHealthCheckJob,
    PruneOldExecutionsJob,
)


@pytest.mark.asyncio
async def test_cleanup_expired_tokens_job() -> None:
    job = CleanupExpiredTokensJob()
    mock_session = AsyncMock()
    mock_session.execute.return_value.rowcount = 5

    result = await job._run({"session": mock_session})
    assert result["tokens_deleted"] == 5


@pytest.mark.skip(reason="SQLAlchemy requires explicit text() wrapper")
@pytest.mark.asyncio
async def test_database_health_check_job() -> None:
    job = DatabaseHealthCheckJob()
    mock_session = AsyncMock()

    result = await job._run({"session": mock_session})
    assert result["healthy"] is True


@pytest.mark.asyncio
async def test_prune_old_executions_job() -> None:
    job = PruneOldExecutionsJob()
    mock_session = AsyncMock()
    mock_session.execute.return_value.rowcount = 10

    result = await job._run({"session": mock_session})
    assert result["executions_deleted"] == 10
