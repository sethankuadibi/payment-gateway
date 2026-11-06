from __future__ import annotations

import hashlib
import json
import uuid
from asyncio import Lock
from typing import Any

from .bank import BankClient, BankError
from .models import (
    GatewayError,
    IdempotencyConflict,
    Payment,
    PaymentNotFound,
    PaymentState,
    utc_now,
)
from .repository import ReceiptRepository


class Service:
    def __init__(self, repository: ReceiptRepository, bank: BankClient):
        self.repository = repository
        self.bank = bank
        self.lock = Lock()

    async def authorize(self, payload: dict[str, Any], key: str) -> dict[str, Any]:
        fingerprint = self._fingerprint(payload)
        async with self.lock:
            replay = self._replay("authorize", key, fingerprint)
            self._validate_amount(payload.get("amount_cents"))
            payment_id = replay[0] if replay is not None else f"pay_{uuid.uuid4().hex}"
            if replay is not None and replay[1] is not None:
                return replay[1]
            pending = self.repository.get_payment(payment_id) if replay is not None else None
            if pending is not None and pending.state == PaymentState.AUTHORIZED:
                response = pending.as_dict()
                self.repository.save_idempotency("authorize", key, fingerprint, response, payment_id)
                return response
            if pending is None:
                now = utc_now()
                pending = Payment(payment_id, payload["order_id"], payload["customer_id"], payload["amount_cents"], "USD", PaymentState.PENDING, now, now)
                self.repository.save_payment(pending)
                self.repository.save_idempotency_pending("authorize", key, fingerprint, payment_id)
            try:
                bank_response = await self.bank.authorize(payment_id, pending.amount_cents, payload["card"], f"gateway:{key}")
            except BankError as exc:
                raise GatewayError(str(exc)) from exc
            authorized = pending.transition(PaymentState.AUTHORIZED, bank_response.reference)
            self.repository.save_payment(authorized, PaymentState.PENDING, bank_response.reference)
            response = authorized.as_dict()
            self.repository.save_idempotency("authorize", key, fingerprint, response, payment_id)
            return response

    async def transition(self, payment_id: str, operation: str, key: str) -> dict[str, Any]:
        async with self.lock:
            payment = self.repository.get_payment(payment_id)
            if payment is None:
                raise PaymentNotFound(f"Payment {payment_id} was not found")
            fingerprint = self._fingerprint({"payment_id": payment_id, "operation": operation})
            replay = self._replay(operation, key, fingerprint)
            if replay is not None:
                _resource_id, response = replay
                if response is not None:
                    return response
                raise GatewayError("A previous request is still being recovered; retry with the same key")
            bank_reference = {
                PaymentState.CAPTURED: payment.bank_authorization_id,
                PaymentState.VOIDED: payment.bank_authorization_id,
                PaymentState.REFUNDED: payment.bank_capture_id,
            }[{
                "capture": PaymentState.CAPTURED,
                "void": PaymentState.VOIDED,
                "refund": PaymentState.REFUNDED,
            }[operation]]
            if not bank_reference:
                raise GatewayError("Payment is missing the bank reference needed for this operation")
            target = {"capture": PaymentState.CAPTURED, "void": PaymentState.VOIDED, "refund": PaymentState.REFUNDED}[operation]
            # Validate the local state machine before causing an external side effect.
            payment.transition(target, "validation-only")
            try:
                bank_response = await getattr(self.bank, operation)(bank_reference, f"gateway:{key}")
            except BankError as exc:
                raise GatewayError(str(exc)) from exc
            updated = payment.transition(target, bank_response.reference)
            self.repository.save_payment(updated, payment.state, bank_response.reference)
            response = updated.as_dict()
            self.repository.save_idempotency(operation, key, fingerprint, response, payment_id)
            return response

    def get(self, payment_id: str) -> dict[str, Any]:
        payment = self.repository.get_payment(payment_id)
        if payment is None:
            raise PaymentNotFound(f"Payment {payment_id} was not found")
        return payment.as_dict()

    def by_order(self, order_id: str) -> list[dict[str, Any]]:
        return [payment.as_dict() for payment in self.repository.find_by_order(order_id)]

    def by_customer(self, customer_id: str) -> list[dict[str, Any]]:
        return [payment.as_dict() for payment in self.repository.find_by_customer(customer_id)]

    def _replay(self, operation: str, key: str, fingerprint: str) -> tuple[str | None, dict[str, Any] | None] | None:
        existing = self.repository.get_idempotency_record(operation, key)
        if existing is None:
            return None
        old_fingerprint, payment_id, response = existing
        if old_fingerprint != fingerprint:
            raise IdempotencyConflict("The idempotency key was already used with a different request")
        return payment_id, response

    @staticmethod
    def _fingerprint(payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _validate_amount(amount: Any) -> None:
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise GatewayError("amount_cents must be a positive integer")
