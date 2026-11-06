from __future__ import annotations

import pytest

from payment_gateway.bank import BankError, BankResponse
from payment_gateway.models import (
    GatewayError,
    IdempotencyConflict,
    InvalidTransition,
    PaymentState,
)
from payment_gateway.repository import ReceiptRepository
from payment_gateway.service import Service


class FakeBank:
    def __init__(self):
        self.calls = []
        self.fail_next = False

    async def authorize(self, payment_id, amount_cents, card, key):
        self.calls.append(("authorize", key))
        if self.fail_next:
            self.fail_next = False
            raise BankError("temporary bank outage", transient=True)
        return BankResponse("bank_auth_1", {"id": "bank_auth_1"})

    async def capture(self, authorization_id, key):
        self.calls.append(("capture", key))
        return BankResponse("bank_capture_1", {"id": "bank_capture_1"})

    async def void(self, authorization_id, key):
        self.calls.append(("void", key))
        return BankResponse("bank_void_1", {"id": "bank_void_1"})

    async def refund(self, capture_id, key):
        self.calls.append(("refund", key))
        return BankResponse("bank_refund_1", {"id": "bank_refund_1"})


def payload():
    return {
        "order_id": "order-1",
        "customer_id": "customer-1",
        "amount_cents": 5000,
        "card": {"number": "4111111111111111", "cvv": "123", "expiry": "12/2030"},
    }


@pytest.fixture
def service():
    bank = FakeBank()
    return Service(ReceiptRepository(), bank), bank


async def test_happy_path_tracks_full_lifecycle(service):
    gateway, _bank = service
    authorized = await gateway.authorize(payload(), "auth-key")
    payment_id = authorized["payment_id"]

    captured = await gateway.transition(payment_id, "capture", "capture-key")
    refunded = await gateway.transition(payment_id, "refund", "refund-key")

    assert authorized["state"] == PaymentState.AUTHORIZED
    assert captured["state"] == PaymentState.CAPTURED
    assert refunded["state"] == PaymentState.REFUNDED
    assert gateway.by_order("order-1")[0]["payment_id"] == payment_id


async def test_duplicate_key_replays_without_calling_bank(service):
    gateway, bank = service
    first = await gateway.authorize(payload(), "same-key")
    second = await gateway.authorize(payload(), "same-key")

    assert second == first
    assert [call[0] for call in bank.calls] == ["authorize"]


async def test_duplicate_transition_key_replays_without_calling_bank(service):
    gateway, bank = service
    authorized = await gateway.authorize(payload(), "auth-key")

    first = await gateway.transition(authorized["payment_id"], "capture", "capture-key")
    second = await gateway.transition(authorized["payment_id"], "capture", "capture-key")

    assert second == first
    assert [call[0] for call in bank.calls] == ["authorize", "capture"]


async def test_reusing_key_with_different_request_is_rejected(service):
    gateway, _bank = service
    await gateway.authorize(payload(), "same-key")
    changed = {**payload(), "amount_cents": 6000}

    with pytest.raises(IdempotencyConflict):
        await gateway.authorize(changed, "same-key")


async def test_invalid_transition_never_calls_bank(service):
    gateway, bank = service
    authorized = await gateway.authorize(payload(), "auth-key")
    await gateway.transition(authorized["payment_id"], "void", "void-key")

    with pytest.raises(InvalidTransition):
        await gateway.transition(authorized["payment_id"], "capture", "capture-key")
    assert [call[0] for call in bank.calls] == ["authorize", "void"]


async def test_failed_bank_call_does_not_create_authorized_receipt(service):
    gateway, bank = service
    bank.fail_next = True

    with pytest.raises(GatewayError, match="temporary bank outage"):
        await gateway.authorize(payload(), "retry-key")

    assert gateway.repository.find_by_order("order-1")[0].state == PaymentState.PENDING


async def test_retry_after_failed_bank_call_recovers_same_payment(service):
    gateway, bank = service
    bank.fail_next = True

    with pytest.raises(GatewayError):
        await gateway.authorize(payload(), "recover-key")

    recovered = await gateway.authorize(payload(), "recover-key")

    assert recovered["state"] == PaymentState.AUTHORIZED
    assert len(gateway.by_order("order-1")) == 1
    assert [call[0] for call in bank.calls] == ["authorize", "authorize"]
