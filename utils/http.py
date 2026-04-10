"""
Shared HTTP utilities: a pre-configured httpx client factory with
automatic retries on transient errors, and a streaming file-download helper.
"""

import logging
from pathlib import Path

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from config import HTTP_BACKOFF_MAX, HTTP_BACKOFF_MIN, HTTP_MAX_RETRIES, HTTP_TIMEOUT

logger = logging.getLogger(__name__)

_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRY_STATUS_CODES
    return isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError))


def build_client(headers: dict | None = None) -> httpx.Client:
    """Return a reusable httpx.Client with sensible defaults."""
    default_headers = {
        "User-Agent": (
            "hydrocscraper/0.1 (+https://github.com/; data research tool)"
        ),
        "Accept-Encoding": "gzip, deflate, br",
    }
    if headers:
        default_headers.update(headers)

    return httpx.Client(
        headers=default_headers,
        timeout=httpx.Timeout(HTTP_TIMEOUT),
        follow_redirects=True,
        http2=True,
    )


def download_file(client: httpx.Client, url: str, dest: Path, **request_kwargs) -> None:
    """
    Stream a file from *url* to *dest*, retrying on transient errors.
    Creates parent directories if they don't exist.
    On failure the partially-written file is removed.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(HTTP_MAX_RETRIES),
        wait=wait_exponential(min=HTTP_BACKOFF_MIN, max=HTTP_BACKOFF_MAX),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _fetch() -> None:
        logger.info("GET %s -> %s", url, dest)
        with client.stream("GET", url, **request_kwargs) as response:
            response.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in response.iter_bytes(chunk_size=65_536):
                    fh.write(chunk)

    try:
        _fetch()
    except Exception:
        if dest.exists():
            dest.unlink()
        raise

    logger.info("Saved %s (%.1f KB)", dest.name, dest.stat().st_size / 1024)
