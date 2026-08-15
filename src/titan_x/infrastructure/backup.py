import asyncio
import datetime
import gzip
import io
import logging

import structlog

logger = structlog.get_logger(__name__)


async def run_database_backup(settings) -> dict:
    """Dump the PostgreSQL database via pg_dump and upload it to an
    S3-compatible bucket (AWS S3, Cloudflare R2, MinIO, ...).

    Returns a dict describing the uploaded object. Raises on failure so the
    caller can log/alert.
    """
    if not settings.backup_enabled:
        logger.info("backup_skipped_disabled")
        return {"skipped": True}

    # pg_dump expects a postgres:// URL, not the asyncpg variant.
    url = str(settings.database_url).replace("+asyncpg", "")

    logger.info("backup_starting")
    proc = await asyncio.create_subprocess_exec(
        "pg_dump",
        url,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--no-comments",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {stderr.decode(errors='replace')[:500]}")

    compressed = gzip.compress(stdout, 9)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = (settings.backup_s3_prefix or "titan-x-backups").strip("/")
    key = f"{prefix}/titan-x-{ts}.sql.gz"

    import aioboto3

    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=settings.backup_s3_endpoint or None,
        aws_access_key_id=settings.backup_s3_access_key,
        aws_secret_access_key=settings.backup_s3_secret_key,
        region_name=settings.backup_s3_region or None,
    ) as s3:
        await s3.upload_fileobj(io.BytesIO(compressed), settings.backup_s3_bucket, key)

    logger.info("backup_completed", key=key, bytes=len(compressed))
    return {"key": key, "bytes": len(compressed), "uncompressed_bytes": len(stdout)}


async def backup_loop(settings) -> None:
    """Run backups on a fixed interval until the process exits."""
    while True:
        try:
            await run_database_backup(settings)
        except Exception:
            logger.exception("backup_failed")
        await asyncio.sleep(max(1, settings.backup_interval_hours) * 3600)
