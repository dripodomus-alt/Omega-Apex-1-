#!/usr/bin/env python3
# ==============================================================================
# webhook_dispatcher.py -- non-blocking outbound observability webhooks.
# ==============================================================================

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


logger = logging.getLogger("omega.webhooks")

WEBHOOK_URLS_ENV = "WEBHOOK_URLS"
DEFAULT_TIMEOUT_SECONDS = 5.0


def configured_webhook_urls(raw: str | None = None) -> tuple[str, ...]:
    """Return configured outbound webhook URLs, restricted to HTTP(S)."""
    source = os.environ.get(WEBHOOK_URLS_ENV, "") if raw is None else raw
    urls: list[str] = []
    for item in source.split(","):
        url = item.strip()
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            urls.append(url)
    return tuple(dict.fromkeys(urls))


def _safe_url_label(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path or '/'}"


def build_webhook_payload(
    event_type: str,
    data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical webhook event envelope."""
    return {
        "schema_version": "omega.webhook.v1",
        "event_type": str(event_type),
        "data": data,
        "metadata": metadata or {},
    }


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[bool, str]:
    body = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "omega-v5-webhook/1"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 0))
            ok = 200 <= status < 300
            return ok, f"http_{status}"
    except HTTPError as exc:
        return False, f"http_{exc.code}"
    except (TimeoutError, URLError) as exc:
        return False, type(exc).__name__
    except Exception as exc:
        return False, type(exc).__name__


async def dispatch_webhook(
    event_type: str,
    data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    *,
    urls: tuple[str, ...] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """
    Dispatch an outbound webhook event.

    This is an observability adapter only. Callers may schedule this coroutine
    with `asyncio.create_task`; it must never control route eligibility,
    simulation outcomes, or transaction broadcast decisions.
    """
    targets = configured_webhook_urls() if urls is None else urls
    payload = build_webhook_payload(event_type, data, metadata)
    if not targets:
        logger.debug("No webhook URLs configured. Skipping event %s.", payload["event_type"])
        return {"attempted": 0, "succeeded": 0, "failed": 0, "results": []}

    tasks = [
        asyncio.to_thread(_post_json, url, payload, max(0.1, float(timeout_seconds)))
        for url in targets
    ]
    raw_results = await asyncio.gather(*tasks)
    results = [
        {"url": _safe_url_label(url), "ok": ok, "detail": detail}
        for url, (ok, detail) in zip(targets, raw_results)
    ]
    succeeded = sum(1 for row in results if row["ok"])
    failed = len(results) - succeeded
    if failed:
        logger.warning(
            "Webhook event %s delivered with failures: succeeded=%s failed=%s",
            payload["event_type"],
            succeeded,
            failed,
        )
    else:
        logger.info("Webhook event %s delivered to %s target(s).", payload["event_type"], succeeded)
    return {"attempted": len(results), "succeeded": succeeded, "failed": failed, "results": results}
