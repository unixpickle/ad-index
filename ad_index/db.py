import asyncio
import hashlib
import json
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from typing import Awaitable, Callable, Iterator, List, Optional, Tuple, TypeVar, Union

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
        await self._conn.commit()

    async def ad_queries(self) -> Iterator[AdQuery]:
        async with self._lock:
            async with await self._retry(
                partial(
                    self._conn.execute,
                    "SELECT ad_query_id, nickname, query, filters FROM ad_queries",
                )
            ) as results:
                async for row in results:
                    yield AdQuery(
                        ad_query_id=row[0],
                        nickname=row[1],
                        query=row[2],
                        filters=json.loads(row[3]),
                    )

    async def insert_ad_query(self, q: AdQuery) -> int:
        async with self._lock:
            result = await self._retry(
                partial(
                    self._conn.execute_insert,
                    "INSERT INTO ad_queries (nickname, query, filters) VALUES (?, ?, ?)",
                    (q.nickname, q.query, json.dumps(q.filters)),
                )
            )
            await self._retry(self._conn.commit)
            return result

    async def update_ad_query(self, q: AdQuery):
        async with self._lock:
            await self._retry_execute(
                "REPLACE INTO ad_queries (ad_query_id, nickname, query, filters) VALUES (?, ?, ?)",
                (q.ad_query_id, q.nickname, q.query, json.dumps(q.filters)),
            )

    async def delete_ad_query(self, id: int):
        async with self._lock:
            await self._retry_execute_commit(
                "DELETE FROM ad_queries WHERE ad_query_id=?", id
            )

    async def create_session(
        self, vapid_pub: bytes, vapid_priv: bytes, session_id: str
    ):
        async with self._lock:
            hash = hash_session_id(session_id)
            await self._retry_execute_commit(
                "INSERT INTO clients (vapid_pub, vapid_priv, session_id, session_hash) VALUES (?, ?, ?, ?)",
                (vapid_pub, vapid_priv, session_id, hash),
            )

    async def update_client_push_sub(
        self, session_id: str, push_sub: Optional[str]
    ) -> bool:
        async with self._lock:
            hash = hash_session_id(session_id)
            count = await self._retry_execute_commit(
                "UPDATE clients SET push_sub=? WHERE session_hash=?",
                (push_sub, hash),
            )
            return count != 0

    async def get_client_push_info(self, session_id: str) -> Optional[ClientPushInfo]:
        async with self._lock:
            hash = hash_session_id(session_id)
            cursor = await self._retry(
                partial(
                    self._conn.execute,
                    "SELECT push_sub, vapid_priv FROM clients WHERE session_hash=?",
                    (hash,),
                )
            )
            async for row in cursor:
                return ClientPushInfo(push_sub=row[0], vapid_priv=row[1])
            return None

    async def push_queue_next(self, retry_timeout: int) -> Optional[PushQueueItem]:
        async with self._lock:
            async with await self._retry(self._conn.cursor) as tx:
                cursor = await tx.execute(
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
                    """
                )
                row = None
                async for row in cursor:
                    break
                if row is None:
                    return None
                id, message, retries, push_sub, vapid_priv = row
                await tx.execute(
                    "UPDATE push_queue SET retry_time=STRFTIME('%s')+?, retries=? WHERE id=?",
                    (retry_timeout, retries + 1, id),
                )
                await tx.execute("commit")
                return PushQueueItem(
                    id=id,
                    push_info=ClientPushInfo(push_sub=push_sub, vapid_priv=vapid_priv),
                    message=message,
                    retries=retries,
                )

    async def push_queue_finish(self, id: int):
        async with self._lock:
            await self._retry_execute_commit("DELETE FROM push_queue WHERE id=?", (id,))

    async def _retry_execute_commit(self, *args) -> int:
        cursor = await self._retry(
            partial(
                self._conn.execute,
                *args,
            )
        )
        count = cursor.rowcount
        await self._retry(self._conn.commit)
        return count

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
