import asyncio
import aiohttp
import logging
import json
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("omega.webhooks")

# Load webhook URLs from environment variable, comma-separated
WEBHOOK_URLS_RAW = os.environ.get("WEBHOOK_URLS", "")
WEBHOOK_URLS = [url.strip() for url in WEBHOOK_URLS_RAW.split(',') if url.strip()]

async def _send_webhook(session: aiohttp.ClientSession, url: str, payload: Dict[str, Any]):
    """Internal helper to send a single webhook."""
    try:
        async with session.post(url, json=payload, timeout=5) as response:
            if response.status != 200:
                logger.warning(f"Webhook to {url} failed with status {response.status}: {await response.text()}")
            else:
                logger.debug(f"Webhook to {url} sent successfully.")
    except aiohttp.ClientError as e:
        logger.error(f"Failed to send webhook to {url}: {e}")
    except asyncio.TimeoutError:
        logger.error(f"Webhook to {url} timed out.")
    except Exception as e:
        logger.error(f"Unexpected error sending webhook to {url}: {e}")

async def dispatch_webhook(event_type: str, data: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None):
    """
    Dispatches a webhook event to all configured URLs.
    This function is non-blocking and will run in the background.
    """
    if not WEBHOOK_URLS:
        logger.debug("No webhook URLs configured. Skipping webhook dispatch.")
        return

    payload = {"event_type": event_type, "data": data, "metadata": metadata if metadata is not None else {}}
    
    # Run the dispatch task in the background to avoid blocking the main loop
    asyncio.create_task(asyncio.create_task(_dispatch_webhook_task(payload)))

async def _dispatch_webhook_task(payload: Dict[str, Any]):
    """Actual asynchronous task for dispatching webhooks."""
    async with aiohttp.ClientSession() as session:
        tasks = [_send_webhook(session, url, payload) for url in WEBHOOK_URLS]
        await asyncio.gather(*tasks)
    logger.info(f"Dispatched webhook for event '{payload['event_type']}' to {len(WEBHOOK_URLS)} URLs.")