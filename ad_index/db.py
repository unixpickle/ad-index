import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from typing import Awaitable, Callable, Iterator, List, Optional, TypeVar

import aiosqlite

R = TypeVar("R")


@dataclass
class AdQuery:
    ad_query_id: Optional[int]
    nickname: str
    query: str
    filters: List[str]


class DB:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

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
                ad_query_id  INTEGER  PRIMARY KEY,
                nickname     TEXT     NOT NULL,
                query        TEXT     NOT NULL,
                filters      TEXT     NOT NULL
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                client_id   INTEGER  PRIMARY KEY,
                vapid_pub   BLOB     NOT NULL,
                vapid_priv  BLOB     NOT NULL,
                push_sub    TEXT
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
        await self._conn.commit()

    async def ad_queries(self) -> Iterator[AdQuery]:
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
        await self._retry(
            partial(
                self._conn.execute,
                "REPLACE INTO ad_queries (ad_query_id, nickname, query, filters) VALUES (?, ?, ?)",
                (q.ad_query_id, q.nickname, q.query, json.dumps(q.filters)),
            )
        )
        await self._retry(self._conn.commit)

    async def delete_ad_query(self, id: int):
        await self._retry(
            partial(
                self._conn.execute, "DELETE FROM ad_queries WHERE ad_query_id=?", id
            )
        )
        await self._retry(self._conn.commit)

    async def _retry(self, fn: Callable[[], Awaitable[R]]) -> R:
        while True:
            try:
                return await fn()
            except sqlite3.OperationalError as exc:
                if "database is locked" in str(exc):
                    await asyncio.sleep(0.01)
                else:
                    raise


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
