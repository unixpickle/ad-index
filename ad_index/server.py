from aiohttp import web
from aiohttp.web import Request

from .client import Client
from .db import DB


class Server:
    def __init__(self, db: DB, client: Client):
        self.db = db
        self.client = client

    async def index(self, request: Request):
        return web.Response(text="Hello world")
