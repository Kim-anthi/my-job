"""Tiny stdlib HTTP helper: retries, timeouts, a polite User-Agent.

Deliberately dependency-free so the worker runs on a bare `python:3.12` image
(or GitHub Actions) with no `pip install` step.
"""
from __future__ import annotations

import gzip
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

USER_AGENT = (
    "job-radar/1.0 (personal job alert bot; "
    "https://github.com/topics/job-board)"
)
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    """A source could not be fetched after all retries."""


def get_bytes(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 25.0,
    retries: int = 3,
    backoff: float = 2.0,
) -> bytes:
    if params:
        clean = {k: v for k, v in params.items() if v not in (None, "")}
        if clean:
            sep = "&" if urllib.parse.urlparse(url).query else "?"
            url = f"{url}{sep}{urllib.parse.urlencode(clean)}"

    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/xml, */*",
        "Accept-Encoding": "gzip",
    }
    request_headers.update(headers or {})

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return body
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in RETRY_STATUS or attempt == retries:
                raise FetchError(f"{url} -> HTTP {exc.code} {exc.reason}") from exc
            wait = _retry_after(exc) or backoff ** attempt
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt == retries:
                raise FetchError(f"{url} -> {exc}") from exc
            wait = backoff ** attempt

        log.warning("fetch failed (%s/%s) %s: %s - retrying in %.0fs",
                    attempt, retries, url, last_error, wait)
        time.sleep(wait)

    raise FetchError(f"{url} -> {last_error}")


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    raw = exc.headers.get("Retry-After") if exc.headers else None
    if not raw:
        return None
    try:
        return min(float(raw), 60.0)
    except ValueError:
        return None


def get_json(url: str, **kwargs: Any) -> Any:
    body = get_bytes(url, **kwargs)
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise FetchError(f"{url} -> invalid JSON: {exc}") from exc


def get_text(url: str, **kwargs: Any) -> str:
    return get_bytes(url, **kwargs).decode("utf-8", "replace")


def post_json(url: str, payload: dict[str, Any], *, timeout: float = 20.0) -> Any:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise FetchError(f"{url} -> HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError(f"{url} -> {exc}") from exc
