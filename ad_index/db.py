import asyncio
import hashlib
import json
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from typing import (
    Any,
    Awaitable,
    Callable,
    Iterator,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

import aiosqlite
from httpx import Client

R = TypeVar("R")


@dataclass
class AdQuery:
    ad_query_id: Optional[int]
    nickname: str
    query: str
    filters: List[str]


@dataclass
class ClientPushInfo:
    push_sub: Optional[str]
    vapid_priv: str


@dataclass
class PushQueueItem:
    id: int
    push_info: ClientPushInfo
    message: str
    retries: int


def transaction(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    async def new_fn(db: "DB", *args, **kwargs) -> Any:
        async with db._lock:
            await db._retry(partial(db._conn.execute, "BEGIN TRANSACTION"))
            try:
                result = await db._retry(partial(fn, db, *args, **kwargs))
            except:
                await db._retry(partial(db._conn.execute, "ROLLBACK"))
                raise
            await db._retry(partial(db._conn.execute, "COMMIT"))
            return result

    return new_fn


class DB:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn
        self._lock = asyncio.Lock()

    @classmethod
    @asynccontextmanager
    async def connect(cls, path: str) -> "DB":
        async with aiosqlite.connect(path) as conn:
            db = cls(conn)
            await db._create_tables()
            yield db

    @transaction
    async def _create_tables(self):
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ad_queries (
                ad_query_id  INTEGER  PRIMARY KEY AUTOINCREMENT,
                nickname     TEXT     NOT NULL,
                query        TEXT     NOT NULL,
                filters      TEXT     NOT NULL
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                client_id     INTEGER   PRIMARY KEY AUTOINCREMENT,
                vapid_pub     BLOB      NOT NULL,
                vapid_priv    BLOB      NOT NULL,
                session_id    CHAR(64)  NOT NULL,
                session_hash  CHAR(64)  NOT NULL,
                push_sub      TEXT
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS client_subs (
                ad_query_id  INTEGER  NOT NULL,
                client_id    INTEGER  NOT NULL,
                UNIQUE(ad_query_id, client_id)
            );
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS push_queue (
                id          INTEGER  PRIMARY KEY,
                client_id   INTEGER  NOT NULL,
                message     TEXT     NOT NULL,
                retry_time  INTEGER  NOT NULL,
                retries     INTEGER  NOT NULL
            );
            """
        )
        await self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS clients_session_hash ON clients(session_hash)
            """
        )
        await self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS push_queue_retry_time ON push_queue(retry_time)
            """
        )

    @transaction
    async def ad_queries(self) -> Iterator[AdQuery]:
        async with await self._conn.execute(
            "SELECT ad_query_id, nickname, query, filters FROM ad_queries"
        ) as results:
            async for row in results:
                yield AdQuery(
                    ad_query_id=row[0],
                    nickname=row[1],
                    query=row[2],
                    filters=json.loads(row[3]),
                )

    @transaction
    async def insert_ad_query(self, q: AdQuery) -> int:
        return await self._conn.execute_insert(
            "INSERT INTO ad_queries (nickname, query, filters) VALUES (?, ?, ?)",
            (q.nickname, q.query, json.dumps(q.filters)),
        )

    @transaction
    async def update_ad_query(self, q: AdQuery) -> bool:
        return (
            await self._conn.execute(
                "REPLACE INTO ad_queries (ad_query_id, nickname, query, filters) VALUES (?, ?, ?)",
                (q.ad_query_id, q.nickname, q.query, json.dumps(q.filters)),
            )
        ).rowcount != 0

    @transaction
    async def delete_ad_query(self, id: int) -> bool:
        return (
            await self._conn.execute(
                "DELETE FROM ad_queries WHERE ad_query_id=?", (id,)
            )
        ).rowcount != 0

    @transaction
    async def create_session(
        self, vapid_pub: bytes, vapid_priv: bytes, session_id: str
    ):
        hash = hash_session_id(session_id)
        await self._conn.execute(
            "INSERT INTO clients (vapid_pub, vapid_priv, session_id, session_hash) VALUES (?, ?, ?, ?)",
            (vapid_pub, vapid_priv, session_id, hash),
        )

    @transaction
    async def update_client_push_sub(
        self, session_id: str, push_sub: Optional[str]
    ) -> bool:
        hash = hash_session_id(session_id)
        count = await self._conn.execute(
            "UPDATE clients SET push_sub=? WHERE session_hash=?",
            (push_sub, hash),
        )
        if count != 0 and not push_sub:
            await self._conn.execute(
                """
                DELETE FROM push_queue WHERE client_id=(
                    SELECT client_id FROM clients WHERE session_hash=?
                )
                """,
                hash,
            )
        return count != 0

    @transaction
    async def push_queue_next(self, retry_timeout: int) -> Optional[PushQueueItem]:
        cursor = await self._conn.execute(
            """
            SELECT
                push_queue.id,
                push_queue.message,
                push_queue.retries,
                clients.push_sub,
                clients.vapid_priv
            FROM push_queue
            LEFT JOIN clients ON clients.client_id = push_queue.client_id
            WHERE retry_time <= STRFTIME('%s')
            ORDER BY retry_time
            """,
        )
        row = None
        async for row in cursor:
            break
        if row is None:
            return None
        id, message, retries, push_sub, vapid_priv = row
        await self._conn.execute(
            "UPDATE push_queue SET retry_time=STRFTIME('%s')+?, retries=? WHERE id=?",
            (retry_timeout, retries + 1, id),
        )
        return PushQueueItem(
            id=id,
            push_info=ClientPushInfo(push_sub=push_sub, vapid_priv=vapid_priv),
            message=message,
            retries=retries,
        )

    @transaction
    async def push_queue_finish(self, id: int):
        await self._conn.execute("DELETE FROM push_queue WHERE id=?", (id,))

    async def _retry(self, fn: Callable[[], Awaitable[R]]) -> R:
        while True:
            try:
                return await fn()
            except sqlite3.OperationalError as exc:
                if "database is locked" in str(exc):
                    await asyncio.sleep(0.01)
                else:
                    raise


def hash_session_id(session_id: Union[str, bytes]) -> str:
    h = hashlib.new("sha256")
    h.update(bytes(session_id, "utf-8") if isinstance(session_id, str) else session_id)
    return h.hexdigest()


async def main():
    async with DB.connect("test.db") as db:
        ad_id = await db.insert_ad_query(
            AdQuery(
                ad_query_id=None,
                nickname="Lilly",
                query="lilly pulitzer",
                filters=["sale", "% off", "discount", "coupon", "code"],
            )
        )
        print([x async for x in db.ad_queries()])
        await db.delete_ad_query(ad_id)


if __name__ == "__main__":
    asyncio.run(main())
