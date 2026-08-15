import pytest

from titan_x.infrastructure import backup


class FakeSettings:
    """Minimal stand-in for Settings, just the fields the backup module touches."""

    def __init__(self, backup_enabled: bool = False, database_url: str = "") -> None:
        self.backup_enabled = backup_enabled
        self.database_url = database_url
        self.backup_s3_endpoint = None
        self.backup_s3_bucket = None
        self.backup_s3_region = None
        self.backup_s3_access_key = None
        self.backup_s3_secret_key = None
        self.backup_s3_prefix = "titan-x-backups"


async def test_run_database_backup_skipped_when_disabled():
    result = await backup.run_database_backup(FakeSettings(backup_enabled=False))
    assert result == {"skipped": True}


async def test_list_backups_empty_when_disabled():
    assert await backup.list_backups(FakeSettings(backup_enabled=False)) == []


async def test_download_backup_raises_when_disabled():
    with pytest.raises(RuntimeError):
        await backup.download_backup(FakeSettings(backup_enabled=False), "k")


async def test_restore_raises_when_disabled():
    with pytest.raises(RuntimeError):
        await backup.restore_from_backup(FakeSettings(backup_enabled=False), "k")


def test_to_psql_url_strips_asyncpg_and_forces_ssl():
    url = backup._to_psql_url(
        FakeSettings(database_url="postgresql+asyncpg://u:p@host:5432/db")
    )
    assert url == "postgresql://u:p@host:5432/db?sslmode=require"


def test_to_psql_url_preserves_existing_query_params():
    url = backup._to_psql_url(
        FakeSettings(database_url="postgresql+asyncpg://u:p@host:5432/db?foo=bar")
    )
    assert url == "postgresql://u:p@host:5432/db?foo=bar&sslmode=require"
