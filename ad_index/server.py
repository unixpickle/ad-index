import base64
import os
import traceback

from aiohttp import web
from aiohttp.web import Request, UrlDispatcher
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from py_vapid.utils import b64urlencode

from .client import Client
from .db import DB, hash_session_id


class Server:
    def __init__(self, asset_dir: str, db: DB, client: Client):
        self.asset_dir = asset_dir
        self.db = db
        self.client = client

    def add_routes(self, router: UrlDispatcher):
        router.add_get("/", self.index)
        router.add_get("/api/create_session", self.api_create_session)
        router.add_static("/", self.asset_dir)

    async def index(self, _request: Request):
        return web.FileResponse(os.path.join(self.asset_dir, "index.html"))

    async def api_create_session(self, _request: Request):
        vapid = Vapid()
        vapid.generate_keys()
        vapid_pub = vapid.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        vapid_priv = vapid.private_pem()
        session_id = hash_session_id(vapid_pub + vapid_priv)
        try:
            await self.db.create_session(
                vapid_pub=vapid_pub, vapid_priv=vapid_priv, session_id=session_id
            )
        except:
            traceback.print_exc()
            return web.json_response(
                data=dict(error="Unable to create session in database.")
            )
        return web.json_response(
            data=dict(
                data=dict(
                    sessionId=session_id,
                    vapidPub=b64urlencode(vapid_pub),
                )
            )
        )
