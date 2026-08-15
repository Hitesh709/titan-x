import asyncio
import datetime
import gzip
import io
import logging

import structlog

logger = structlog.get_logger(__name__)


def _to_psql_url(settings) -> str:
    """Convert the async SQLAlchemy URL into one `psql` can use, forcing SSL."""
    url = str(settings.database_url).replace("+asyncpg", "")
    return url + ("?sslmode=require" if "?" not in url else "&sslmode=require")


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


async def list_backups(settings) -> list[dict]:
    """List available backups in the configured bucket (newest last)."""
    if not settings.backup_enabled:
        return []
    import aioboto3

    session = aioboto3.Session()
    prefix = (settings.backup_s3_prefix or "titan-x-backups").strip("/")
    out: list[dict] = []
    async with session.client(
        "s3",
        endpoint_url=settings.backup_s3_endpoint or None,
        aws_access_key_id=settings.backup_s3_access_key,
        aws_secret_access_key=settings.backup_s3_secret_key,
        region_name=settings.backup_s3_region or None,
    ) as s3:
        paginator = s3.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=settings.backup_s3_bucket, Prefix=f"{prefix}/"):
            for obj in page.get("Contents", []):
                out.append(
                    {
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": str(obj.get("LastModified")),
                    }
                )
    out.sort(key=lambda x: x["key"])
    return out


async def restore_from_backup(settings, key: str | None = None) -> dict:
    """Download a gzip SQL dump from S3 and restore it via psql.

    If *key* is omitted the most recent backup is restored. This is a
    disruptive maintenance operation: it drops and recreates database objects.
    """
    if not settings.backup_enabled:
        raise RuntimeError("Backups are not configured (BACKUP_ENABLED=false)")

    import aioboto3
    import io

    session = aioboto3.Session()
    prefix = (settings.backup_s3_prefix or "titan-x-backups").strip("/")
    async with session.client(
        "s3",
        endpoint_url=settings.backup_s3_endpoint or None,
        aws_access_key_id=settings.backup_s3_access_key,
        aws_secret_access_key=settings.backup_s3_secret_key,
        region_name=settings.backup_s3_region or None,
    ) as s3:
        if key is None:
            backups = await list_backups(settings)
            if not backups:
                raise RuntimeError("No backups found in the configured bucket")
            key = backups[-1]["key"]

        buf = io.BytesIO()
        await s3.download_fileobj(settings.backup_s3_bucket, key, buf)
        data = gzip.decompress(buf.getvalue())

    # pg_dump uses postgres:// (not the asyncpg variant); force SSL for Render.
    url = _to_psql_url(settings)

    logger.info("restore_starting", key=key, bytes=len(data))
    proc = await asyncio.create_subprocess_exec(
        "psql",
        url,
        "-v",
        "ON_ERROR_STOP=1",
        "-f",
        "-",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate(input=data)
    if proc.returncode != 0:
        raise RuntimeError(f"psql restore failed: {stderr.decode(errors='replace')[:1000]}")

    logger.info("restore_completed", key=key)
    return {"restored_key": key, "bytes": len(data)}


async def download_backup(settings, key: str) -> tuple[bytes, str]:
    """Download a backup object from S3 and return its raw (gzipped) bytes."""
    if not settings.backup_enabled:
        raise RuntimeError("Backups are not configured (BACKUP_ENABLED=false)")

    import aioboto3
    import io

    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=settings.backup_s3_endpoint or None,
        aws_access_key_id=settings.backup_s3_access_key,
        aws_secret_access_key=settings.backup_s3_secret_key,
        region_name=settings.backup_s3_region or None,
    ) as s3:
        buf = io.BytesIO()
        await s3.download_fileobj(settings.backup_s3_bucket, key, buf)
        return buf.getvalue(), key


async def backup_loop(settings) -> None:
    """Run backups on a fixed interval until the process exits."""
    while True:
        try:
            await run_database_backup(settings)
        except Exception:
            logger.exception("backup_failed")
        await asyncio.sleep(max(1, settings.backup_interval_hours) * 3600)
