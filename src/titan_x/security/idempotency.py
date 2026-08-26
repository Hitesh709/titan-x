"""Idempotency key validation for financial write operations."""
from __future__ import annotations

import re

from fastapi import HTTPException, Request, status

_KEY = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")


def require_idempotency_key(request: Request) -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not _KEY.fullmatch(key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid Idempotency-Key is required for this operation",
        )
    return key
