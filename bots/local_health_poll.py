import asyncio
import logging
import os

from services.db import pg
from services.local_signals.aggregator import assemble_for_zip
from services.local_signals.cache import upsert_zip_payload

LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


async def main() -> None:
    rows = pg.fetch("select distinct zip from app.user_locations where zip is not null")
    for row in rows:
        zip_code = row.get("zip")
        if not zip_code:
            continue
        try:
            payload = await assemble_for_zip(zip_code)
            upsert_zip_payload(zip_code, payload)
            logger.info("[poll] cached %s", zip_code)
        except Exception as exc:
            logger.exception("[poll] %s failed: %s", zip_code, exc)


if __name__ == "__main__":
    asyncio.run(main())
