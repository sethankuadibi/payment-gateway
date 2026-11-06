from fastapi.testclient import TestClient

from payment_gateway.api import create_app
from payment_gateway.bank import BankResponse
from payment_gateway.repository import ReceiptRepository
from payment_gateway.service import Service


class Bank:
    async def authorize(self, payment_id, amount_cents, card, key):
        return BankResponse("auth", {})

    async def capture(self, authorization_id, key):
        return BankResponse("capture", {})

    async def void(self, authorization_id, key):
        return BankResponse("void", {})

    async def refund(self, capture_id, key):
        return BankResponse("refund", {})


def client():
    return TestClient(create_app(Service(ReceiptRepository(), Bank())))


def test_api_requires_idempotency_key():
    response = client().post(
        "/payments/authorize",
        json={
            "order_id": "order-1",
            "customer_id": "customer-1",
            "amount_cents": 100,
            "card": {"number": "4111111111111111", "cvv": "123", "expiry": "12/2030"},
        },
    )

    assert response.status_code == 400
    assert "Idempotency-Key" in response.json()["detail"]


def test_api_authorizes_and_replays_request():
    request = {
        "order_id": "order-1",
        "customer_id": "customer-1",
        "amount_cents": 100,
        "card": {"number": "4111111111111111", "cvv": "123", "expiry": "12/2030"},
    }
    api = client()
    response = api.post("/payments/authorize", json=request, headers={"Idempotency-Key": "key"})
    replay = api.post("/payments/authorize", json=request, headers={"Idempotency-Key": "key"})

    assert response.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["payment_id"] == response.json()["payment_id"]
