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
    List,
    Optional,
    Sequence,
    Set,
    TypeVar,
    Union,
)

import aiosqlite

R = TypeVar("R")

MAX_NOTIFY_CHARS = 128  # don't send big push notifications


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
    client_id: int
    push_info: ClientPushInfo
    message: str
    retries: int


@dataclass
class AdContent:
    ad_query_id: int
    id: str
    account_name: str
    account_url: str
    start_date: int
    last_seen: int
    text: str

    def to_json(self) -> Dict[str, Any]:
        return dict(
            adQueryId=str(self.ad_query_id),
            id=self.id,
            accountName=self.account_name,
            accountUrl=self.account_url,
            startDate=self.start_date,
            lastSeen=self.last_seen,
            text=self.text,
        )


@dataclass
class AdQueryStatus(AdQueryResult):
    next_pull: int
    last_pull: Optional[int]
    last_error: Optional[str]
    last_notify: Optional[int]

    def to_json(self) -> Dict[str, Any]:
        res = super().to_json()
        res.update(
            dict(
                nextPull=self.next_pull,
                lastPull=self.last_pull,
                lastError=self.last_error,
                lastNotify=self.last_notify,
            )
        )
        return res


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
            await db._conn.execute("PRAGMA foreign_keys = ON")
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
                next_pull    INTEGER  NOT NULL,
                last_pull    INTEGER,
                last_error   TEXT,
                last_notify  INTEGER,
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
                push_sub      TEXT,
                last_seen     INTEGER   NOT NULL,
                UNIQUE(session_hash)
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS client_subs (
                ad_query_id  INTEGER  NOT NULL  REFERENCES ad_queries(ad_query_id) ON DELETE CASCADE,
                client_id    INTEGER  NOT NULL  REFERENCES clients(client_id) ON DELETE CASCADE,
                UNIQUE(ad_query_id, client_id)
            );
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS push_queue (
                id          INTEGER  PRIMARY KEY  AUTOINCREMENT,
                client_id   INTEGER  NOT NULL  REFERENCES clients(client_id) ON DELETE CASCADE,
                message     TEXT     NOT NULL,
                retry_time  INTEGER  NOT NULL,
                retries     INTEGER  NOT NULL
            );
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ad_content (
                ad_query_id   INTEGER   NOT NULL  REFERENCES ad_queries(ad_query_id) ON DELETE CASCADE,
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
                ad_query_id  INTEGER   NOT NULL  REFERENCES ad_queries(ad_query_id) ON DELETE CASCADE,
                text_hash    CHAR(64)  NOT NULL,
                text         TEXT      NOT NULL,
                last_seen    INTEGER   NOT NULL,
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
            LEFT JOIN client_subs ON (
                client_subs.ad_query_id = ad_queries.ad_query_id
                AND client_subs.client_id = (
                    SELECT client_id FROM clients WHERE clients.session_hash = ?
                )
            )
            {f'WHERE ad_queries.ad_query_id = ?' if ad_query_id is not None else ''}
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
            """
            INSERT INTO ad_queries (
                nickname,
                query,
                filters,
                next_pull
            ) VALUES (?, ?, ?, STRFTIME('%s'))
            """,
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
                (
                    await self._conn.execute(
                        """
                        UPDATE ad_queries SET
                            nickname=?,
                            query=?,
                            filters=?,
                            next_pull=STRFTIME('%s'),
                            last_notify=NULL
                        WHERE ad_query_id=?
                        """,
                        (q.nickname, q.query, json.dumps(q.filters), q.ad_query_id),
                    )
                ).rowcount
                != 0
            )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc):
                raise DataArgumentError("name is already in use")
            raise
        updated_sub = await self._toggle_ad_query_subscription(
            q.ad_query_id, session_id, q.subscribed
        )
        return dict(updated_data=updated_data, updated_sub=updated_sub)

    @transaction
    async def ad_query_next(self, refresh_interval: int) -> Optional[AdQuery]:
        cursor = await self._conn.execute(
            """
            SELECT ad_query_id, nickname, query, filters
            FROM ad_queries
            WHERE next_pull < CAST(STRFTIME('%s') AS INTEGER)
            ORDER BY next_pull
            LIMIT 1
            """,
        )
        row = None
        async for row in cursor:
            break
        if row is None:
            return None
        id, nickname, query, filters = row
        await self._conn.execute(
            "UPDATE ad_queries SET next_pull=STRFTIME('%s')+? WHERE ad_query_id=?",
            (refresh_interval, id),
        )
        return AdQuery(
            nickname=nickname, query=query, filters=json.loads(filters), ad_query_id=id
        )

    @transaction
    async def ad_query_finished_pull(
        self, ad_query_id: int, error: Optional[str] = None
    ):
        await self._conn.execute(
            """
            UPDATE ad_queries SET last_pull=STRFTIME('%s'), last_error=? WHERE ad_query_id=?
            """,
            (error, ad_query_id),
        )

    @transaction
    async def ad_query_status(
        self, session_id: str, ad_query_id: int
    ) -> Optional[AdQueryStatus]:
        hash = hash_session_id(session_id)
        rows = await self._conn.execute_fetchall(
            """
            SELECT
                nickname,
                query,
                filters,
                next_pull,
                last_pull,
                last_error,
                last_notify,
                (
                    SELECT COUNT(*) FROM client_subs
                    WHERE (
                        client_subs.ad_query_id = ad_queries.ad_query_id AND
                        client_subs.client_id = (
                            SELECT clients.client_id FROM clients WHERE session_hash=?
                        )
                    )
                )
            FROM ad_queries
            WHERE ad_query_id=?
            """,
            (hash, ad_query_id),
        )
        if not len(rows):
            return None
        (
            nickname,
            query,
            filters,
            next_pull,
            last_pull,
            last_error,
            last_notify,
            subscribed,
        ) = rows[0]
        return AdQueryStatus(
            nickname=nickname,
            query=query,
            filters=filters,
            ad_query_id=ad_query_id,
            subscribed=bool(subscribed),
            next_pull=next_pull,
            last_pull=last_pull,
            last_error=last_error,
            last_notify=last_notify,
        )

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
        return deleted

    @transaction
    async def create_session(
        self, vapid_pub: bytes, vapid_priv: bytes, session_id: str
    ):
        hash = hash_session_id(session_id)
        await self._conn.execute(
            """
            INSERT INTO clients (vapid_pub, vapid_priv, session_id, session_hash, last_seen)
            VALUES (?, ?, ?, ?, STRFTIME('%s'))
            """,
            (vapid_pub, vapid_priv, session_id, hash),
        )

    @transaction
    async def session_exists(self, session_id: str) -> bool:
        hash = hash_session_id(session_id)
        count = await self._fetchone(
            "SELECT COUNT(*) FROM clients WHERE session_hash=?", (hash,)
        )
        return count == (1,)

    @transaction
    async def cleanup_sessions(self, expiration_time: int):
        await self._conn.execute(
            """
            DELETE FROM clients WHERE last_seen < STRFTIME('%s') - ?
            """,
            (expiration_time,),
        )

    @transaction
    async def update_client_push_sub(
        self, session_id: str, push_sub: Optional[str]
    ) -> bool:
        if json.loads(push_sub) is None:
            # Store NULL as sql type and not JSON string.
            push_sub = None
        hash = hash_session_id(session_id)
        c1 = self._conn.total_changes
        await self._conn.execute(
            "UPDATE clients SET push_sub=?, last_seen=STRFTIME('%s') WHERE session_hash=?",
            (push_sub, hash),
        )
        count = self._conn.total_changes - c1
        if count and not push_sub:
            await self._conn.execute(
                """
                DELETE FROM push_queue WHERE client_id=(
                    SELECT client_id FROM clients WHERE session_hash=?
                )
                """,
                (hash,),
            )
        return count != 0

    @transaction
    async def push_queue_next(self, retry_timeout: int) -> Optional[PushQueueItem]:
        cursor = await self._conn.execute(
            """
            SELECT
                push_queue.id,
                push_queue.client_id,
                push_queue.message,
                push_queue.retries,
                clients.push_sub,
                clients.vapid_priv
            FROM push_queue
            LEFT JOIN clients ON clients.client_id = push_queue.client_id
            WHERE retry_time <= CAST(STRFTIME('%s') AS INTEGER)
            ORDER BY retry_time
            """,
        )
        row = None
        async for row in cursor:
            break
        if row is None:
            return None
        id, client_id, message, retries, push_sub, vapid_priv = row
        await self._conn.execute(
            "UPDATE push_queue SET retry_time=STRFTIME('%s')+?, retries=? WHERE id=?",
            (retry_timeout, retries + 1, id),
        )
        return PushQueueItem(
            id=id,
            client_id=client_id,
            push_info=ClientPushInfo(push_sub=push_sub, vapid_priv=vapid_priv),
            message=message,
            retries=retries,
        )

    @transaction
    async def push_queue_finish(self, id: int, unsub_client: bool = False):
        if unsub_client:
            await self._conn.execute(
                """
                UPDATE clients SET push_sub=NULL WHERE client_id=(
                    SELECT client_id FROM push_queue WHERE id=?
                )
                """,
                (id,),
            )
        else:
            # If the client successfully received a notification, we don't want
            # to expire the client session.
            await self._conn.execute(
                """
                UPDATE clients SET last_seen=STRFTIME('%s') WHERE client_id=(
                    SELECT client_id FROM push_queue WHERE id=?
                )
                """,
                (id,),
            )
        await self._conn.execute("DELETE FROM push_queue WHERE id=?", (id,))

    @transaction
    async def unseen_ad_ids(self, ad_query_id: int, ids: Sequence[str]) -> Set[str]:
        cursor = await self._conn.execute(
            """
            SELECT id FROM ad_content
            WHERE ad_query_id=? AND id IN (SELECT value FROM json_each(?))
            """,
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
        text_expiration: int,
        min_notify_interval: int,
    ) -> bool:
        queries = await self._conn.execute_fetchall(
            "SELECT nickname FROM ad_queries WHERE ad_query_id=?",
            (ad_query_id,),
        )
        if not len(queries):
            return False
        nickname = queries[0][0]

        text_hash = hash_session_id(text.lower())
        inserted = await self._conn.execute_insert(
            """
            INSERT OR REPLACE INTO ad_content (
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
                text_expiration,
            ),
        )
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO ad_content_text
            (ad_query_id, text_hash, text, last_seen)
            VALUES (?, ?, ?, STRFTIME('%s'))
            """,
            (ad_query_id, text_hash, text),
        )
        (should_notify,) = await self._fetchone(
            """
            SELECT last_notify IS NULL OR last_notify < STRFTIME('%s') - ?
            FROM ad_queries
            WHERE ad_query_id=?
            """,
            (min_notify_interval, ad_query_id),
        )
        if not count and should_notify:
            notify_message = json.dumps(
                dict(
                    adQueryId=ad_query_id,
                    nickname=nickname,
                    ad=dict(
                        id=id,
                        accountName=account_name,
                        accountUrl=account_url,
                        text=text[:MAX_NOTIFY_CHARS],
                    ),
                )
            )
            await self._conn.execute(
                """
                INSERT INTO push_queue (client_id, message, retry_time, retries)
                SELECT client_id, ?, STRFTIME('%s'), 0
                FROM client_subs
                WHERE ad_query_id=? AND EXISTS (
                    SELECT 1 FROM clients
                    WHERE clients.client_id=client_subs.client_id AND clients.push_sub IS NOT NULL
                )
                """,
                (notify_message, ad_query_id),
            )
            await self._conn.execute(
                """
                UPDATE ad_queries SET last_notify=STRFTIME('%s') WHERE ad_query_id=?
                """,
                (ad_query_id,),
            )
        return True

    @transaction
    async def cleanup_ads(self, max_ads: int, text_expiration: int):
        large_queries = await self._conn.execute_fetchall(
            """
            SELECT ad_query_id FROM ad_content
            GROUP BY ad_query_id
            HAVING COUNT(*) > ?
            """,
            (max_ads,),
        )
        for (ad_query_id,) in large_queries:
            await self._conn.execute(
                """
                DELETE FROM ad_content WHERE rowid IN (
                    SELECT rowid FROM ad_content
                    WHERE ad_query_id=?
                    ORDER BY last_seen DESC, start_date DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (ad_query_id, max_ads),
            )
        # We retain text hashes even after the ads are gone to prevent duplicate
        # notifications over short spans of time.
        await self._conn.execute(
            """
            DELETE FROM ad_content_text
            WHERE (
                last_seen < STRFTIME('%s') - ?
                AND NOT EXISTS (
                    SELECT 1 FROM ad_content
                    WHERE (
                        ad_content.ad_query_id = ad_content_text.ad_query_id
                        AND ad_content.text_hash = ad_content_text.text_hash
                    )
                )
            )
            """,
            (text_expiration,),
        )

    @transaction
    async def list_ad_content(self, ad_query_id: int) -> List[AdContent]:
        if await self._fetchone(
            "SELECT COUNT(*) FROM ad_queries WHERE ad_query_id=?", (ad_query_id,)
        ) == (0,):
            raise DataArgumentError(f"no ad_query_id found: {ad_query_id}")
        cursor = await self._conn.execute(
            """
            SELECT ad_query_id, id, account_name, account_url, start_date, last_seen, text
            FROM ad_content
            WHERE ad_query_id=?
            ORDER BY last_seen DESC, start_date DESC
            """,
            (ad_query_id,),
        )
        results = []
        async for row in cursor:
            results.append(
                AdContent(
                    ad_query_id=row[0],
                    id=row[1],
                    account_name=row[2],
                    account_url=row[3],
                    start_date=row[4],
                    last_seen=row[5],
                    text=row[6],
                )
            )
        return results

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
        await db.push_queue_finish(0, True)


if __name__ == "__main__":
    asyncio.run(main())
