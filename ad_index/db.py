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
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
    TypeVar,
    Union,
)

import aiosqlite

R = TypeVar("R")


class DataArgumentError(Exception):
    pass


@dataclass
class AdQueryBase:
    nickname: str
    query: str
    filters: List[str]


@dataclass
class AdQuery(AdQueryBase):
    ad_query_id: int


@dataclass
class AdQueryResult(AdQuery):
    subscribed: bool

    def to_json(self) -> Dict[str, Any]:
        return dict(
            adQueryId=str(self.ad_query_id),
            nickname=self.nickname,
            query=self.query,
            filters=self.filters,
            subscribed=self.subscribed,
        )


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
    def __init__(
        self, conn: aiosqlite.Connection, text_hash_expiration: int = 60 * 60 * 24 * 5
    ):
        self._conn = conn
        self._lock = asyncio.Lock()
        self.text_hash_expiration = text_hash_expiration

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
                filters      TEXT     NOT NULL,
                UNIQUE(nickname)
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
            CREATE TABLE IF NOT EXISTS ad_content (
                ad_query_id   INTEGER   NOT NULL,
                id            TEXT      NOT NULL,
                account_name  TEXT      NOT NULL,
                account_url   TEXT      NOT NULL,
                start_date    INTEGER   NOT NULL,
                last_seen     INTEGER   NOT NULL,
                text_hash     CHAR(64)  NOT NULL,
                text          TEXT      NOT NULL,
                screenshot    BLOB      NOT NULL,
                UNIQUE(ad_query_id, id)
            );
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ad_content_text (
                ad_query_id  INTEGER   NOT NULL,
                text_hash    CHAR(64)  NOT NULL,
                text         TEXT      NOT NULL,
                last_seen    INTEGER   PRIMARY KEY,
                UNIQUE(ad_query_id, text_hash)
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
        await self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS ad_content_text_seen_date ON ad_content_text(last_seen)
            """
        )

    @transaction
    async def ad_queries(
        self, session_id: str, ad_query_id: Optional[int] = None
    ) -> List[AdQueryResult]:
        hash = hash_session_id(session_id)
        cursor = await self._conn.execute(
            f"""
            SELECT ad_queries.ad_query_id, nickname, query, filters, client_subs.client_id
            FROM ad_queries
            LEFT JOIN client_subs ON client_subs.ad_query_id = ad_queries.ad_query_id
            WHERE (
                client_subs.client_id IS NULL OR
                client_subs.client_id = (
                    SELECT client_id FROM clients WHERE clients.session_hash = ?
                )
            ) {f'AND ad_queries.ad_query_id = ?' if ad_query_id is not None else ''}
            """,
            (hash, *([ad_query_id] if ad_query_id is not None else [])),
        )
        results = []
        async for row in cursor:
            results.append(
                AdQueryResult(
                    nickname=row[1],
                    query=row[2],
                    filters=json.loads(row[3]),
                    ad_query_id=str(row[0]),
                    subscribed=row[4] is not None,
                )
            )
        return results

    @transaction
    async def insert_ad_query(
        self, q: AdQueryBase, sub_session_id: Optional[str] = None
    ) -> Optional[int]:
        if sub_session_id:
            hash = hash_session_id(sub_session_id)
            client_id = None
            async for row in await self._conn.execute(
                "SELECT client_id FROM clients WHERE session_hash=?", (hash,)
            ):
                (client_id,) = row
                break
            if client_id is None:
                return None
        result = await self._conn.execute_insert(
            "INSERT INTO ad_queries (nickname, query, filters) VALUES (?, ?, ?)",
            (q.nickname, q.query, json.dumps(q.filters)),
        )
        (id,) = result
        if sub_session_id:
            await self._conn.execute_insert(
                "INSERT INTO client_subs (ad_query_id, client_id) VALUES (?, ?)",
                (id, client_id),
            )
        return id

    @transaction
    async def update_ad_query(
        self, q: AdQueryResult, session_id: str
    ) -> Dict[str, Any]:
        try:
            updated_data = (
                await self._conn.execute(
                    "UPDATE ad_queries SET nickname=?, query=?, filters=? WHERE ad_query_id=?",
                    (q.nickname, q.query, json.dumps(q.filters), q.ad_query_id),
                )
            ).rowcount != 0
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc):
                raise DataArgumentError("name is already in use")
            raise
        updated_sub = await self._toggle_ad_query_subscription(
            q.ad_query_id, session_id, q.subscribed
        )
        return dict(updated_data=updated_data, updated_sub=updated_sub)

    @transaction
    async def toggle_ad_query_subscription(
        self, ad_query_id: int, session_id: str, subscribed: bool
    ) -> bool:
        return await self._toggle_ad_query_subscription(
            ad_query_id, session_id, subscribed
        )

    async def _toggle_ad_query_subscription(
        self, ad_query_id: int, session_id: str, subscribed: bool
    ) -> bool:
        hash = hash_session_id(session_id)
        client_id = None
        async for row in await self._conn.execute(
            "SELECT client_id FROM clients WHERE session_hash=?", (hash,)
        ):
            (client_id,) = row
        if client_id is None:
            return False
        exists = await self._conn.execute(
            "SELECT EXISTS(SELECT * FROM ad_queries WHERE ad_query_id=?)",
            (ad_query_id,),
        )
        if not exists:
            return False
        if subscribed:
            await self._conn.execute(
                "REPLACE INTO client_subs (ad_query_id, client_id) VALUES (?, ?)",
                (ad_query_id, client_id),
            )
        else:
            await self._conn.execute(
                "DELETE FROM client_subs WHERE ad_query_id=? AND client_id=?",
                (ad_query_id, client_id),
            )
        return True

    @transaction
    async def delete_ad_query(self, id: int) -> bool:
        deleted = (
            await self._conn.execute(
                "DELETE FROM ad_queries WHERE ad_query_id=?", (id,)
            )
        ).rowcount != 0
        await self._conn.execute("DELETE FROM client_subs WHERE ad_query_id=?", (id,))
        await self._conn.execute("DELETE FROM ad_content WHERE ad_query_id=?", (id,))
        await self._conn.execute(
            "DELETE FROM ad_content_text WHERE ad_query_id=?", (id,)
        )
        return deleted

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

    @transaction
    async def unseen_ad_ids(self, ad_query_id: int, ids: Sequence[str]) -> Set[str]:
        cursor = await self._conn.execute(
            "SELECT id from ad_content WHERE ad_query_id=? AND id IN json_each(?)",
            (ad_query_id, json.dumps(list(ids))),
        )
        seen = set()
        async for row in cursor:
            seen.add(row[0])
        return set(x for x in ids if x not in seen)

    @transaction
    async def insert_ad(
        self,
        ad_query_id: int,
        id: str,
        account_name: str,
        account_url: str,
        start_date: int,
        text: str,
        screenshot: bytes,
    ) -> bool:
        if await self._fetchone(
            "SELECT COUNT(*) FROM ad_queries WHERE ad_query_id=?",
            (ad_query_id,),
        ) != (1,):
            return False
        text_hash = hash_session_id(text.lower())
        inserted = await self._conn.execute_insert(
            """
            INSERT OR IGNORE INTO ad_content (
                ad_query_id,
                id,
                account_name,
                account_url,
                start_date,
                text_hash,
                text,
                screenshot,
                last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, STRFTIME('%s'))
            """,
            (
                ad_query_id,
                id,
                account_name,
                account_url,
                start_date,
                text_hash,
                text,
                screenshot,
            ),
        )
        if not inserted:
            return False
        (count,) = await self._fetchone(
            """
            SELECT COUNT(*) FROM ad_content_text
            WHERE ad_query_id=? AND text_hash=? AND last_seen > STRFTIME('%s') - ?
            """,
            (
                ad_query_id,
                text_hash,
                self.text_hash_expiration,
            ),
        )
        await self._conn.execute(
            """
            REPLACE INTO ad_content_text
            (ad_query_id, text_hash, text, last_seen)
            VALUES (?, ?, ?, STRFTIME('%s'))
            """,
            (ad_query_id, text_hash, text),
        )
        if not count:
            notify_message = json.dumps(
                dict(
                    ad_query_id=ad_query_id,
                    id=id,
                    account_name=account_name,
                    account_url=account_url,
                    text=text,
                )
            )
            await self._conn.execute(
                """
                INSERT INTO push_queue (client_id, message, retry_time, retries)
                SELECT client_id, ?, STRFTIME('%s'), 0
                FROM client_subs
                WHERE ad_query_id=?
                """,
                (notify_message, ad_query_id),
            )
        return True

    async def _fetchone(self, *args) -> sqlite3.Row:
        results = list(await self._conn.execute_fetchall(*args))
        if len(results) != 1:
            raise sqlite3.OperationalError(f"expected 1 result but got {len(results)}")
        return results[0]

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
