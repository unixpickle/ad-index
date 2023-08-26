import asyncio
import io
import json
import os
import sqlite3
import traceback
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from aiohttp import web
from aiohttp.web import Request, UrlDispatcher
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from py_vapid.utils import b64urlencode

from .client import Client
from .db import DB, AdQuery, AdQueryResult, hash_session_id
from .notifier import Notifier


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


def rewrite_db_errors(
    fn: Callable[..., Awaitable[Any]]
) -> Callable[..., Awaitable[web.Response]]:
    async def _fn(*args) -> web.Response:
        try:
            return await fn(*args)
        except sqlite3.IntegrityError as exc:
            # "UNIQUE constraint failed: ad_queries.nickname"
            if "UNIQUE" in str(exc) and "nickname" in str(exc):
                raise APIError("nickname is not unique")
            raise

    return _fn


class Server:
    def __init__(
        self,
        *,
        asset_dir: str,
        db: DB,
        client: Client,
        notifier: Notifier,
        max_message_retries: int,
        message_retry_interval: int,
        refresh_interval: int,
        ad_text_expiration: int,
        max_ad_history: int,
    ):
        self.asset_dir = asset_dir
        self.db = db
        self.client = client
        self.notifier = notifier
        self.max_message_retries = max_message_retries
        self.message_retry_interval = message_retry_interval
        self.refresh_interval = refresh_interval
        self.ad_text_expiration = ad_text_expiration
        self.max_ad_history = max_ad_history
        asyncio.create_task(self._push_queue_loop())
        asyncio.create_task(self._query_loop())

    def add_routes(self, router: UrlDispatcher):
        router.add_get("/", self.index)
        router.add_get("/api/create_session", self.api_create_session)
        router.add_get("/api/update_push_sub", self.api_update_push_sub)
        router.add_get("/api/get_ad_queries", self.api_get_ad_queries)
        router.add_get("/api/get_ad_query", self.api_get_ad_query)
        router.add_get("/api/insert_ad_query", self.api_insert_ad_query)
        router.add_get("/api/update_ad_query", self.api_update_ad_query)
        router.add_get("/api/delete_ad_query", self.api_delete_ad_query)
        router.add_get(
            "/api/toggle_ad_query_subscription", self.api_toggle_ad_query_subscription
        )
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
        return dict(
            sessionId=session_id,
            vapidPub=b64urlencode(vapid_pub),
        )

    @api_method
    async def api_update_push_sub(self, request: Request):
        session_id = request.query.getone("session_id")
        push_sub = request.query.getone("push_sub") or None
        if push_sub is not None:
            try:
                obj = json.loads(push_sub)
                if obj is not None:
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

    @api_method
    async def api_get_ad_queries(self, request: Request) -> List[Dict[str, Any]]:
        session_id = request.query.getone("session_id")
        results = []
        for item in await self.db.ad_queries(session_id):
            results.append(item.to_json())
        return results

    @api_method
    async def api_get_ad_query(self, request: Request) -> Dict[str, Any]:
        try:
            session_id = request.query.getone("session_id")
            ad_query_id = int(request.query.getone("ad_query_id"))
        except KeyError as exc:
            raise APIError(f"argument not found: {exc}")
        except json.JSONDecodeError as exc:
            raise APIError(f"failed to parse argument: {exc}")
        for item in await self.db.ad_queries(session_id, ad_query_id=ad_query_id):
            return item.to_json()
        raise APIError("could not find the specified ad_query")

    @api_method
    @rewrite_db_errors
    async def api_insert_ad_query(self, request: Request) -> str:
        session_id, ad_query = parse_ad_query_request(request, update=False)
        result_id = await self.db.insert_ad_query(
            ad_query,
            sub_session_id=(session_id if ad_query.subscribed else None),
        )
        if result_id is None:
            raise APIError("session_id was not found")
        return str(result_id)

    @api_method
    @rewrite_db_errors
    async def api_update_ad_query(self, request: Request) -> Dict[str, Any]:
        session_id, ad_query = parse_ad_query_request(request, update=True)
        try:
            return await self.db.update_ad_query(ad_query, session_id)
        except sqlite3.IntegrityError as exc:
            # "UNIQUE constraint failed: ad_queries.nickname"
            if "UNIQUE" in str(exc) and "nickname" in str(exc):
                raise APIError("nickname is not unique")
            raise

    @api_method
    async def api_delete_ad_query(self, request: Request) -> bool:
        ad_query_id = request.query.getone("ad_query_id")
        return await self.db.delete_ad_query(ad_query_id)

    @api_method
    async def api_toggle_ad_query_subscription(self, request: Request):
        try:
            session_id = request.query.getone("session_id")
            ad_query_id = int(request.query.getone("ad_query_id"))
            subscribed = json.loads(request.query.getone("subscribed"))
        except KeyError as exc:
            raise APIError(f"argument not found: {exc}")
        except ValueError as exc:
            raise APIError(f"failed to parse arument: {exc}")
        status = await self.db.toggle_ad_query_subscription(
            ad_query_id=ad_query_id,
            session_id=session_id,
            subscribed=subscribed,
        )
        if not status:
            raise APIError("either ad_query_id or session_id was invalid")

    async def _push_queue_loop(self):
        while True:
            item = await self.db.push_queue_next(
                retry_timeout=self.message_retry_interval
            )
            if item is None:
                await asyncio.sleep(10.0)
                continue
            status = None
            try:
                status = await self.notifier.notify(item.push_info, item.message)
            except:
                traceback.print_exc()
            if status == 201 or item.retries >= self.max_message_retries:
                await self.db.push_queue_finish(item.id, unsub_client=status != 201)

    async def _query_loop(self):
        await self.db.cleanup_ads(
            max_ads=self.max_ad_history, text_expiration=self.ad_text_expiration
        )
        while True:
            query: Optional[AdQuery] = await self.db.ad_query_next(
                refresh_interval=self.refresh_interval
            )
            if query is None:
                await asyncio.sleep(10.0)
                continue
            try:
                results = [
                    result
                    for result in await self.client.query(query.query)
                    if not len(query.filters)
                    or any(x.tolower() in result.text.lower() for x in query.filters)
                ]
            except Exception as exc:
                self.db.ad_query_finished_pull(
                    ad_query_id=query.ad_query_id, error=str(exc)
                )
                continue
            new_ids = await self.db.unseen_ad_ids(
                query.ad_query_id, [x.id for x in results]
            )
            screenshots = await self.client.screenshot_ids(list(new_ids))
            print(sorted(screenshots.keys()))
            print(sorted(new_ids))
            id_to_result = {x.id: x for x in results}
            for id in new_ids:
                result = id_to_result[id]
                data = io.BytesIO()
                if id in screenshots:
                    screenshot = screenshots[id]
                    screenshot.convert("RGB").save(data, format="JPEG", quality=85)
                await self.db.insert_ad(
                    ad_query_id=query.ad_query_id,
                    id=result.id,
                    account_name=result.account_name,
                    account_url=result.account_url,
                    start_date=result.start_date,
                    text=result.text,
                    screenshot=data.getvalue(),
                    text_expiration=self.ad_text_expiration,
                )
            await self.db.ad_query_finished_pull(ad_query_id=query.ad_query_id)
            await self.db.cleanup_ads(
                max_ads=self.max_ad_history, text_expiration=self.ad_text_expiration
            )


def parse_ad_query_request(request: Request, update: bool) -> Tuple[str, AdQueryResult]:
    try:
        session_id = request.query.getone("session_id")
        nickname = request.query.getone("nickname")
        query = request.query.getone("query")
        filters = json.loads(request.query.getone("filters"))
        subscribed = json.loads(request.query.getone("subscribed"))
        if update:
            ad_query_id = int(request.query.getone("ad_query_id"))
        else:
            ad_query_id = None
    except KeyError as exc:
        raise APIError(f"argument not found: {exc}")
    except json.JSONDecodeError as exc:
        raise APIError(f"failed to parse argument: {exc}")
    if not isinstance(filters, list) or not all(isinstance(x, str) for x in filters):
        raise APIError("filters must be a JSON-encoded array of strings")
    if not isinstance(subscribed, bool):
        raise APIError("subscribed must be true or false")
    return (
        session_id,
        AdQueryResult(
            nickname=nickname,
            query=query,
            filters=filters,
            ad_query_id=ad_query_id,
            subscribed=subscribed,
        ),
    )
