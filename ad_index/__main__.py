import argparse
import asyncio
import logging
import os

from aiohttp import web

from .client import Client
from .db import DB
from .notifier import Notifier
from .server import Server

DEFAULT_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=str, default="ad_index.db")
    parser.add_argument("--asset-dir", type=str, default=DEFAULT_ASSET_DIR)
    parser.add_argument("--vapid-sub", type=str, default="mailto:alex@aqnichol.com")
    parser.add_argument("--max-message-retries", type=int, default=3)
    parser.add_argument("--message-retry-interval", type=int, default=60 * 30)
    parser.add_argument("--refresh-interval", type=int, default=60 * 30)
    parser.add_argument("--ad-text-expiration", type=int, default=60 * 60 * 24 * 5)
    parser.add_argument("--min-notify-interval", type=int, default=60 * 5)
    parser.add_argument("--max-ad-history", type=int, default=50)
    parser.add_argument("--session-expiration", type=int, default=60 * 60 * 24 * 120)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    async with DB.connect(args.db) as db:
        async with Client.create() as client:
            server = Server(
                asset_dir=args.asset_dir,
                db=db,
                client=client,
                notifier=Notifier(vapid_sub=args.vapid_sub),
                max_message_retries=args.max_message_retries,
                message_retry_interval=args.message_retry_interval,
                refresh_interval=args.refresh_interval,
                ad_text_expiration=args.ad_text_expiration,
                min_notify_interval=args.min_notify_interval,
                max_ad_history=args.max_ad_history,
                session_expiration=args.session_expiration,
            )
            app = web.Application()
            server.add_routes(app.router)

            # https://stackoverflow.com/questions/53465862/python-aiohttp-into-existing-event-loop
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host=args.host, port=args.port)
            await site.start()
            await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
