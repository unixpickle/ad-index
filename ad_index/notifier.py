import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

import requests
from py_vapid import Vapid
from pywebpush import webpush

from .db import ClientPushInfo


class Notifier:
    def __init__(self, vapid_sub: str):
        self.vapid_sub = vapid_sub
        self.executor = ThreadPoolExecutor(1)
        self.session = requests.Session()

    async def notify(self, info: ClientPushInfo, message: str) -> int:
        return await asyncio.get_running_loop().run_in_executor(
            self.executor,
            lambda: webpush(
                json.loads(info.push_sub),
                data=message,
                vapid_private_key=Vapid.from_pem(info.vapid_priv),
                vapid_claims={"sub": self.vapid_sub},
            ).status_code,
        )
