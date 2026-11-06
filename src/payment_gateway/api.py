from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .bank import HttpBankClient
from .models import GatewayError, PaymentNotFound
from .repository import ReceiptRepository
from .service import Service


class Card(BaseModel):
    number: str = Field(min_length=12, max_length=19)
    cvv: str = Field(min_length=3, max_length=4)
    expiry: str


class AuthorizationRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=128)
    customer_id: str = Field(min_length=1, max_length=128)
    amount_cents: int = Field(gt=0)
    card: Card


def create_app(service: Service | None = None) -> FastAPI:
    app = FastAPI(title="FicMart Payment Gateway", version="0.1.0")
    if service is None:
        database = os.environ.get("DATABASE_URL", "gateway.sqlite3")
        bank_url = os.environ.get("BANK_URL", "http://localhost:8787")
        service = Service(ReceiptRepository(database), HttpBankClient(bank_url))
    app.state.service = service

    @app.exception_handler(GatewayError)
    async def gateway_error_handler(_request: Request, exc: GatewayError):
        code = status.HTTP_404_NOT_FOUND if isinstance(exc, PaymentNotFound) else status.HTTP_409_CONFLICT
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/payments/authorize", status_code=201)
    async def authorize(body: AuthorizationRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
        if not idempotency_key:
            raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
        return await app.state.service.authorize(body.model_dump(), idempotency_key)

    async def operation(payment_id: str, action: str, idempotency_key: str | None):
        if not idempotency_key:
            raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
        return await app.state.service.transition(payment_id, action, idempotency_key)

    @app.post("/payments/{payment_id}/capture")
    async def capture(payment_id: str, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
        return await operation(payment_id, "capture", idempotency_key)

    @app.post("/payments/{payment_id}/void")
    async def void(payment_id: str, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
        return await operation(payment_id, "void", idempotency_key)

    @app.post("/payments/{payment_id}/refund")
    async def refund(payment_id: str, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
        return await operation(payment_id, "refund", idempotency_key)

    @app.get("/payments/{payment_id}")
    async def get_payment(payment_id: str):
        return app.state.service.get(payment_id)

    @app.get("/orders/{order_id}/payments")
    async def order_payments(order_id: str):
        return {"payments": app.state.service.by_order(order_id)}

    @app.get("/customers/{customer_id}/payments")
    async def customer_payments(customer_id: str):
        return {"payments": app.state.service.by_customer(customer_id)}

    return app


app = create_app()
