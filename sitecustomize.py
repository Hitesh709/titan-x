"""Runtime compatibility for the free Render + Neon deployment.

Keep the secret DATABASE_URL in Render unchanged, but route Neon pooled hosts
used by the application to the branch's direct read/write endpoint. This is
needed for startup schema inspection, which is not safe through PgBouncer.
"""

import os
from urllib.parse import urlsplit, urlunsplit


_database_url = os.environ.get("DATABASE_URL", "")
if "-pooler" in _database_url:
    _parts = urlsplit(_database_url)
    _hostname = (_parts.hostname or "").replace("-pooler", "", 1)
    _authority = _hostname
    if _parts.port is not None:
        _authority += f":{_parts.port}"
    if _parts.username is not None:
        _authority = _parts.username + (
            ":" + _parts.password if _parts.password is not None else ""
        ) + "@" + _authority
    os.environ["DATABASE_URL"] = urlunsplit(
        (_parts.scheme, _authority, _parts.path, _parts.query, _parts.fragment)
    )
