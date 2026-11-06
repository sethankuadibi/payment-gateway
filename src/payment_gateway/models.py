from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class PaymentState(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    VOIDED = "voided"
    REFUNDED = "refunded"


ALLOWED_TRANSITIONS: dict[PaymentState, frozenset[PaymentState]] = {
    PaymentState.PENDING: frozenset({PaymentState.AUTHORIZED}),
    PaymentState.AUTHORIZED: frozenset({PaymentState.CAPTURED, PaymentState.VOIDED}),
    PaymentState.CAPTURED: frozenset({PaymentState.REFUNDED}),
    PaymentState.VOIDED: frozenset(),
    PaymentState.REFUNDED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class Payment:
    payment_id: str
    order_id: str
    customer_id: str
    amount_cents: int
    currency: str
    state: PaymentState
    created_at: str
    updated_at: str
    bank_authorization_id: str | None = None
    bank_capture_id: str | None = None
    bank_void_id: str | None = None
    bank_refund_id: str | None = None

    def transition(self, target: PaymentState, bank_reference: str) -> Payment:
        if target not in ALLOWED_TRANSITIONS[self.state]:
            raise InvalidTransition(f"Cannot move payment from {self.state} to {target}")
        refs = {
            "bank_authorization_id": self.bank_authorization_id,
            "bank_capture_id": self.bank_capture_id,
            "bank_void_id": self.bank_void_id,
            "bank_refund_id": self.bank_refund_id,
        }
        key = {
            PaymentState.AUTHORIZED: "bank_authorization_id",
            PaymentState.CAPTURED: "bank_capture_id",
            PaymentState.VOIDED: "bank_void_id",
            PaymentState.REFUNDED: "bank_refund_id",
        }[target]
        refs[key] = bank_reference
        return Payment(
            payment_id=self.payment_id,
            order_id=self.order_id,
            customer_id=self.customer_id,
            amount_cents=self.amount_cents,
            currency=self.currency,
            state=target,
            created_at=self.created_at,
            updated_at=utc_now(),
            **refs,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "payment_id": self.payment_id,
            "order_id": self.order_id,
            "customer_id": self.customer_id,
            "amount_cents": self.amount_cents,
            "currency": self.currency,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "bank_authorization_id": self.bank_authorization_id,
            "bank_capture_id": self.bank_capture_id,
            "bank_void_id": self.bank_void_id,
            "bank_refund_id": self.bank_refund_id,
        }


class GatewayError(RuntimeError):
    """Base error mapped to a safe client response."""


class InvalidTransition(GatewayError):
    pass


class IdempotencyConflict(GatewayError):
    pass


class PaymentNotFound(GatewayError):
    pass
