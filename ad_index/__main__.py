import argparse
import asyncio

from aiohttp import web

from .client import Client
from .db import DB
from .server import Server


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=str, default="ad_index.db")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    async with DB.connect(args.db) as db:
        async with Client.create() as client:
            server = Server(db=db, client=client)
            app = web.Application()
            app.add_routes([web.get("/", server.index)])

            # https://stackoverflow.com/questions/53465862/python-aiohttp-into-existing-event-loop
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host=args.host, port=args.port)
            await site.start()
            await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
