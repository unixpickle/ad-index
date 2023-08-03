import base64
import json
import os
import traceback
from typing import Any, Awaitable, Callable

from aiohttp import web
from aiohttp.web import Request, UrlDispatcher
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from py_vapid.utils import b64urlencode

from .client import Client
from .db import DB, hash_session_id


class APIError(Exception):
    pass


def api_method(
    fn: Callable[..., Awaitable[Any]]
) -> Callable[..., Awaitable[web.Response]]:
    async def _fn(*args) -> web.Response:
        try:
            data = await fn(*args)
        except Exception as exc:
            traceback.print_exc()
            return web.json_response(data=dict(error=str(exc)))
        return web.json_response(data=dict(data=data))

    return _fn


class Server:
    def __init__(self, asset_dir: str, db: DB, client: Client):
        self.asset_dir = asset_dir
        self.db = db
        self.client = client

    def add_routes(self, router: UrlDispatcher):
        router.add_get("/", self.index)
        router.add_get("/api/create_session", self.api_create_session)
        router.add_get("/api/update_push_sub", self.api_update_push_sub)
        router.add_static("/", self.asset_dir)

    async def index(self, _request: Request):
        return web.FileResponse(os.path.join(self.asset_dir, "index.html"))

    @api_method
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
        except Exception as exc:
            raise APIError("Unable to create session in database") from exc
        return web.json_response(
            data=dict(
                data=dict(
                    sessionId=session_id,
                    vapidPub=b64urlencode(vapid_pub),
                )
            )
        )

    @api_method
    async def api_update_push_sub(self, request: Request):
        session_id = request.query.getone("session_id")
        push_sub = request.query.getone("push_sub") or None
        if push_sub is not None:
            try:
                obj = json.loads(push_sub)
                if not isinstance(obj["endpoint"], str):
                    raise APIError("bad endpoint field")
                if not isinstance(obj["keys"], dict):
                    raise APIError("bad keys field")
                if not isinstance(obj["keys"]["auth"], str):
                    raise APIError("bad keys/auth field")
                if not isinstance(obj["keys"]["p256dh"], str):
                    raise APIError("bad keys/p256dh field")
            except KeyError as exc:
                raise APIError(f"missing key in push_sub: {str(exc)}")
            except json.JSONDecodeError as exc:
                raise APIError(f"push_sub is not valid JSON: {str(exc)}")
        found = await self.db.update_client_push_sub(
            session_id=session_id, push_sub=push_sub
        )
        if not found:
            raise APIError("session_id not found")
