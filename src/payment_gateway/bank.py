from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class BankError(RuntimeError):
    def __init__(self, message: str, transient: bool = False):
        super().__init__(message)
        self.transient = transient


@dataclass(frozen=True, slots=True)
class BankResponse:
    reference: str
    raw: dict[str, Any]


class BankClient(Protocol):
    async def authorize(self, payment_id: str, amount_cents: int, card: dict[str, str], key: str) -> BankResponse: ...
    async def capture(self, authorization_id: str, key: str) -> BankResponse: ...
    async def void(self, authorization_id: str, key: str) -> BankResponse: ...
    async def refund(self, capture_id: str, key: str) -> BankResponse: ...


class HttpBankClient:
    def __init__(self, base_url: str, retries: int = 3, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self.client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.client.aclose()

    async def _post(self, path: str, payload: dict[str, Any], key: str) -> BankResponse:
        for attempt in range(self.retries):
            try:
                response = await self.client.post(
                    f"{self.base_url}{path}", json=payload, headers={"Idempotency-Key": key}
                )
                if response.status_code >= 500:
                    raise BankError("bank server error", transient=True)
                if response.status_code >= 400:
                    detail = response.json().get("detail", "bank rejected request")
                    raise BankError(str(detail))
                body = response.json()
                return BankResponse(str(body.get("id") or body.get("reference")), body)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt + 1 == self.retries:
                    raise BankError("bank request timed out", transient=True) from exc
                await asyncio.sleep((2**attempt) + random.uniform(0, 0.25))
            except BankError as exc:
                if not exc.transient or attempt + 1 == self.retries:
                    raise
                await asyncio.sleep((2**attempt) + random.uniform(0, 0.25))
        raise AssertionError("unreachable")

    async def authorize(self, payment_id, amount_cents, card, key):
        return await self._post("/api/v1/authorizations", {"payment_id": payment_id, "amount_cents": amount_cents, **card}, key)

    async def capture(self, authorization_id, key):
        return await self._post("/api/v1/captures", {"authorization_id": authorization_id}, key)

    async def void(self, authorization_id, key):
        return await self._post("/api/v1/voids", {"authorization_id": authorization_id}, key)

    async def refund(self, capture_id, key):
        return await self._post("/api/v1/refunds", {"capture_id": capture_id}, key)

