import argparse
import asyncio
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
    parser.add_argument("--message-retry-interval", type=int, default=120)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    async with DB.connect(args.db) as db:
        async with Client.create() as client:
            server = Server(
                asset_dir=args.asset_dir,
                db=db,
                client=client,
                notifier=Notifier(vapid_sub=args.vapid_sub),
                max_message_retries=args.max_message_retries,
                message_retry_interval=args.message_retry_interval,
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
