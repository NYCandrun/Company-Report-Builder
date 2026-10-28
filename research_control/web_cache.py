"""Run-local shared URL ledger and content-addressed public-response cache.

The cache is transport infrastructure, not evidence. Research and brand workers
may reuse the same public bytes, but each remains responsible for admitting the
material into its own evidence system and applying its own scope rules.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from collections.abc import Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from research_control.hashing import sha256_file
from research_control.io import atomic_write_json, utc_now
from research_control.runtime import RuntimeStore


CACHE_ROOT = "tools/outputs/web-cache"
CACHE_OBJECTS = f"{CACHE_ROOT}/objects"
CACHE_LEDGER = f"{CACHE_ROOT}/ledger.json"
TRACKING_PARAMETERS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "referrer", "source",
    "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term",
}


def normalize_ledger_url(value: str) -> str:
    """Normalize identity without making research-channel classification claims."""
    parsed = urlparse(value.strip())
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("shared-cache URL must be an absolute public http(s) URL")
    host = parsed.hostname.casefold().rstrip(".")
    port = parsed.port
    netloc = host
    if port and not ((parsed.scheme.casefold() == "http" and port == 80) or (parsed.scheme.casefold() == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(
        sorted(
            (key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() not in TRACKING_PARAMETERS
        ),
        doseq=True,
    )
    return urlunparse((parsed.scheme.casefold(), netloc, path, "", query, ""))


@dataclass(frozen=True)
class SharedResponse:
    requested_url: str
    final_url: str
    content_type: str
    status: int
    headers: dict[str, str]
    body: bytes
    object_path: str
    content_sha256: str
    cache_hit: bool


class SharedWebCache:
    """Coordinate concurrent workers through SQLite and immutable byte objects."""

    def __init__(self, root: Path, store: RuntimeStore) -> None:
        self.root = root.resolve()
        self.store = store
        (self.root / CACHE_OBJECTS).mkdir(parents=True, exist_ok=True)

    def note_url(
        self,
        url: str,
        *,
        consumer: str,
        purpose: str,
        discovered_from: str = "",
    ) -> str:
        normalized = normalize_ledger_url(url)
        now = utc_now()
        with self.store.connection:
            self.store.connection.execute(
                """
                INSERT INTO shared_urls(url, state, first_seen_at, updated_at)
                VALUES (?, 'registered', ?, ?)
                ON CONFLICT(url) DO UPDATE SET updated_at=excluded.updated_at
                """,
                (normalized, now, now),
            )
            self.store.connection.execute(
                """
                INSERT INTO shared_url_uses(
                    url, consumer, purpose, discovered_from, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(url, consumer, purpose) DO UPDATE SET
                    discovered_from=CASE
                        WHEN excluded.discovered_from!='' THEN excluded.discovered_from
                        ELSE shared_url_uses.discovered_from
                    END,
                    last_seen_at=excluded.last_seen_at
                """,
                (normalized, consumer, purpose, discovered_from, now, now),
            )
        return normalized

    def lookup(self, url: str, *, consumer: str, purpose: str) -> SharedResponse | None:
        normalized = normalize_ledger_url(url)
        row = self.store.connection.execute(
            """
            SELECT * FROM shared_urls
            WHERE state='fetched' AND (url=? OR final_url=?)
            ORDER BY CASE WHEN url=? THEN 0 ELSE 1 END, fetched_at DESC
            LIMIT 1
            """,
            (normalized, normalized, normalized),
        ).fetchone()
        if not row:
            self.note_url(normalized, consumer=consumer, purpose=purpose)
            return None
        record = dict(row)
        self.note_url(str(record["url"]), consumer=consumer, purpose=purpose)
        relative = str(record.get("object_path") or "")
        path = self.root / relative
        expected = str(record.get("content_sha256") or "")
        if not relative or not path.is_file() or sha256_file(path) != expected:
            with self.store.connection:
                self.store.connection.execute(
                    "UPDATE shared_urls SET state='registered', updated_at=? WHERE url=?",
                    (utc_now(), record["url"]),
                )
            return None
        return SharedResponse(
            requested_url=normalized,
            final_url=str(record.get("final_url") or record["url"]),
            content_type=str(record.get("content_type") or "application/octet-stream"),
            status=int(record.get("status_code") or 200),
            headers=json.loads(record.get("headers_json") or "{}"),
            body=path.read_bytes(),
            object_path=relative,
            content_sha256=expected,
            cache_hit=True,
        )

    def store_response(
        self,
        url: str,
        *,
        final_url: str,
        content_type: str,
        status: int,
        headers: dict[str, str] | None,
        body: bytes,
        consumer: str,
        purpose: str,
        discovered_from: str = "",
    ) -> SharedResponse:
        normalized = self.note_url(
            url, consumer=consumer, purpose=purpose, discovered_from=discovered_from
        )
        final = normalize_ledger_url(final_url)
        digest = sha256(body).hexdigest()
        suffix = (
            ".html" if content_type in {"text/html", "application/xhtml+xml"}
            else ".xml" if "xml" in content_type
            else ".json" if content_type == "application/json"
            else ".css" if content_type == "text/css"
            else ".svg" if content_type == "image/svg+xml"
            else ".pdf" if content_type == "application/pdf"
            else ".bin"
        )
        relative = f"{CACHE_OBJECTS}/{digest}{suffix}"
        target = self.root / relative
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(body)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, target)
            except Exception:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                raise
        now = utc_now()
        header_values = {str(key): str(value) for key, value in (headers or {}).items()}
        with self.store.connection:
            self.store.connection.execute(
                """
                UPDATE shared_urls SET state='fetched', final_url=?, content_type=?,
                    status_code=?, headers_json=?, content_sha256=?, object_path=?,
                    content_bytes=?, fetched_at=?, updated_at=?
                WHERE url=?
                """,
                (
                    final, content_type, int(status), json.dumps(header_values, sort_keys=True),
                    digest, relative, len(body), now, now, normalized,
                ),
            )
        return SharedResponse(
            requested_url=normalized,
            final_url=final,
            content_type=content_type,
            status=int(status),
            headers=header_values,
            body=body,
            object_path=relative,
            content_sha256=digest,
            cache_hit=False,
        )

    def fetch_or_reuse(
        self,
        url: str,
        *,
        consumer: str,
        purpose: str,
        fetcher: Callable[[], Any],
        discovered_from: str = "",
        wait_seconds: float = 35.0,
    ) -> SharedResponse:
        """Atomically select one fetcher while concurrent consumers wait for its bytes."""
        cached = self.lookup(url, consumer=consumer, purpose=purpose)
        if cached is not None:
            return cached
        normalized = self.note_url(
            url, consumer=consumer, purpose=purpose, discovered_from=discovered_from
        )
        deadline = time.monotonic() + wait_seconds
        while True:
            now = utc_now()
            with self.store.connection:
                claimed = self.store.connection.execute(
                    "UPDATE shared_urls SET state='fetching', updated_at=? "
                    "WHERE url=? AND state='registered'",
                    (now, normalized),
                ).rowcount
            if claimed:
                try:
                    response = fetcher()
                    return self.store_response(
                        normalized,
                        final_url=str(response.url),
                        content_type=str(response.content_type),
                        status=int(response.status),
                        headers=dict(getattr(response, "headers", {}) or {}),
                        body=bytes(response.body),
                        consumer=consumer,
                        purpose=purpose,
                        discovered_from=discovered_from,
                    )
                except Exception:
                    with self.store.connection:
                        self.store.connection.execute(
                            "UPDATE shared_urls SET state='registered', updated_at=? "
                            "WHERE url=? AND state='fetching'",
                            (utc_now(), normalized),
                        )
                    raise
            cached = self.lookup(url, consumer=consumer, purpose=purpose)
            if cached is not None:
                return cached
            if time.monotonic() >= deadline:
                # A dead fetch owner must not block the run. The late worker may
                # refetch, and content addressing still converges on one object.
                response = fetcher()
                return self.store_response(
                    normalized,
                    final_url=str(response.url),
                    content_type=str(response.content_type),
                    status=int(response.status),
                    headers=dict(getattr(response, "headers", {}) or {}),
                    body=bytes(response.body),
                    consumer=consumer,
                    purpose=purpose,
                    discovered_from=discovered_from,
                )
            time.sleep(0.25)

    def records(self, *, purpose: str | None = None, state: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[str] = []
        if state:
            clauses.append("u.state=?")
            values.append(state)
        if purpose:
            clauses.append("EXISTS (SELECT 1 FROM shared_url_uses x WHERE x.url=u.url AND x.purpose=?)")
            values.append(purpose)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.store.connection.execute(
            f"SELECT u.* FROM shared_urls u{where} ORDER BY u.url", values
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["headers"] = json.loads(record.pop("headers_json") or "{}")
            uses = self.store.connection.execute(
                "SELECT consumer, purpose, discovered_from, first_seen_at, last_seen_at "
                "FROM shared_url_uses WHERE url=? ORDER BY purpose, consumer",
                (record["url"],),
            ).fetchall()
            record["uses"] = [dict(item) for item in uses]
            result.append(record)
        return result

    def export_ledger(self) -> Path:
        path = self.root / CACHE_LEDGER
        atomic_write_json(path, {
            "schema_version": "1.0.0",
            "note": "Transport/cache ledger only; entries are not research or brand evidence by themselves.",
            "urls": self.records(),
            "exported_at": utc_now(),
        })
        return path
