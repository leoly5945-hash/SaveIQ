"""Amazon Creators API — the one approved source of Amazon product images.

The Associates agreement only allows Amazon images obtained through Amazon's
own tools, so the site showed category icons until this existed. We ask
``getItems`` for ``images.primary.large`` and keep only the URL: the image is
served by Amazon's CDN, never copied, and the URL is refreshed within a day.

Access needs an approved Associates account *and* 10 qualifying sales in the
past 30 days. Until then every call fails ("AssociateNotEligible"); the client
then stops calling for a while and the site keeps showing icons. Nothing here
ever raises: an image is a nice-to-have.

Limits (Creators API docs, 2026-10): 1 request per second, 8,640 per day, up to
10 ASINs per ``getItems``. Access tokens last an hour and are reused.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import urlsplit

import httpx

_TOKEN_URL = "https://api.amazon.com/auth/o2/token"  # NA credentials (v3.1): US, CA, MX, BR
_GET_ITEMS_URL = "https://creatorsapi.amazon/catalog/v1/getItems"
_SCOPE = "creatorsapi::default"
_RESOURCE = "images.primary.large"
_BATCH = 10
_MIN_INTERVAL_SECONDS = 1.05
_IMAGE_TTL_SECONDS = 20 * 3600  # refresh well inside a day
_MISS_TTL_SECONDS = 6 * 3600  # an ASIN with no image: don't re-ask on every page view
_BACKOFF_SECONDS = 3600  # after any failure (not eligible yet, throttled, down)
_TIMEOUT_SECONDS = 8.0
# Only Amazon's own image CDN may end up in an <img> on our pages.
_IMAGE_HOSTS = frozenset({"m.media-amazon.com", "images-na.ssl-images-amazon.com"})

logger = logging.getLogger(__name__)


def _describe_failure(exc: Exception) -> str:
    """A short reason safe to log and show: status + Amazon's error code, never a credential."""

    if isinstance(exc, httpx.HTTPStatusError):
        step = "token" if exc.request.url.host.startswith("api.") else "getItems"
        code = ""
        try:
            body = exc.response.json()
            errors = body.get("errors") if isinstance(body, dict) else None
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                code = str(errors[0].get("code") or "")
            elif isinstance(body, dict):
                code = str(body.get("error") or body.get("code") or body.get("__type") or "")
        except ValueError:
            code = ""
        return f"{step} HTTP {exc.response.status_code} {code}".strip()[:120]
    return type(exc).__name__


def _safe_image_url(url: Any) -> str | None:
    if not isinstance(url, str):
        return None
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in _IMAGE_HOSTS:
        return None
    return url


class AmazonCreatorsClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        partner_tag: str,
        marketplace: str = "www.amazon.ca",
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._partner_tag = partner_tag
        self._marketplace = marketplace
        self._transport = transport
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._last_call_at: float | None = None
        self._blocked_until = 0.0
        self.last_error: str | None = None
        self.images_fetched = 0
        # asin -> (expires_at, url or None when Amazon has no image for it)
        self._images: dict[str, tuple[float, str | None]] = {}

    def cached(self, asins: Iterable[str]) -> dict[str, str]:
        """Images we already hold. Never calls Amazon."""

        now = self._clock()
        found: dict[str, str] = {}
        for asin in asins:
            hit = self._images.get(asin.upper())
            if hit and hit[0] > now and hit[1]:
                found[asin.upper()] = hit[1]
        return found

    def missing(self, asins: Iterable[str]) -> list[str]:
        now = self._clock()
        out: list[str] = []
        for asin in asins:
            key = asin.upper()
            hit = self._images.get(key)
            if (hit is None or hit[0] <= now) and key not in out:
                out.append(key)
        return out

    def warm(self, asins: Iterable[str]) -> None:
        """Fetch images for ASINs not in the cache. Blocking; never raises."""

        with self._lock:  # one caller at a time keeps us under 1 request/second
            todo = self.missing(asins)
            if not todo or self._clock() < self._blocked_until:
                return
            try:
                with httpx.Client(transport=self._transport, timeout=_TIMEOUT_SECONDS) as client:
                    for start in range(0, len(todo), _BATCH):
                        self._fetch_batch(client, todo[start : start + _BATCH])
                self.last_error = None
            except Exception as exc:  # noqa: BLE001 - not eligible yet, throttled, or down
                self._blocked_until = self._clock() + _BACKOFF_SECONDS
                self.last_error = _describe_failure(exc)
                logger.warning("Amazon Creators API unavailable: %s", self.last_error)

    def status(self) -> str:
        """``ok`` once images have come back, ``untried``, or the last failure."""

        if self.last_error:
            return f"error: {self.last_error}"
        return "ok" if self.images_fetched else "untried"

    def image_for(self, asin: str) -> str | None:
        """One product's image, fetching it if needed. Blocking; never raises."""

        self.warm([asin])
        return self.cached([asin]).get(asin.upper())

    def _fetch_batch(self, client: httpx.Client, batch: list[str]) -> None:
        token = self._app_token(client)
        self._pace()
        resp = client.post(
            _GET_ITEMS_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "x-marketplace": self._marketplace,
            },
            json={
                "itemIds": batch,
                "itemIdType": "ASIN",
                "marketplace": self._marketplace,
                "partnerTag": self._partner_tag,
                "resources": [_RESOURCE],
            },
        )
        resp.raise_for_status()
        items = ((resp.json().get("itemsResult") or {}).get("items")) or []
        now = self._clock()
        urls: dict[str, str | None] = {}
        for item in items:
            asin = str(item.get("asin") or "").upper()
            primary = ((item.get("images") or {}).get("primary")) or {}
            urls[asin] = _safe_image_url((primary.get("large") or {}).get("url"))
        for asin in batch:
            url = urls.get(asin)
            self._images[asin] = (now + (_IMAGE_TTL_SECONDS if url else _MISS_TTL_SECONDS), url)
            self.images_fetched += 1 if url else 0

    def _app_token(self, client: httpx.Client) -> str:
        if self._token and self._clock() < self._token_expires_at:
            return self._token
        self._pace()
        resp = client.post(
            _TOKEN_URL,
            json={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": _SCOPE,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = str(body["access_token"])
        self._token_expires_at = self._clock() + max(60, int(body.get("expires_in", 3600)) - 300)
        return self._token

    def _pace(self) -> None:
        now = self._clock()
        if self._last_call_at is not None:
            wait = _MIN_INTERVAL_SECONDS - (now - self._last_call_at)
            if wait > 0:
                self._sleep(wait)
        self._last_call_at = self._clock()


_client: AmazonCreatorsClient | None = None
_client_key: tuple[str, str, str] | None = None


def get_creators_client(settings: Any) -> AmazonCreatorsClient | None:
    """Process-wide client (keeps the token + image cache), or ``None`` unconfigured."""

    global _client, _client_key
    cid, secret = settings.amazon_creators_client_id, settings.amazon_creators_client_secret
    if not cid or not secret:
        return None
    key = (cid, secret, settings.amazon_associate_tag)
    if _client is None or _client_key != key:
        _client = AmazonCreatorsClient(cid, secret, partner_tag=settings.amazon_associate_tag)
        _client_key = key
    return _client
