from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import Payment, PaymentState


class ReceiptRepository:
    def __init__(self, database: str | Path = ":memory:"):
        self.connection = sqlite3.connect(str(database), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                bank_authorization_id TEXT,
                bank_capture_id TEXT,
                bank_void_id TEXT,
                bank_refund_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_id);
            CREATE INDEX IF NOT EXISTS idx_payments_customer ON payments(customer_id);
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                operation TEXT NOT NULL,
                key TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                response_json TEXT,
                PRIMARY KEY (operation, key)
            );
            CREATE TABLE IF NOT EXISTS payment_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id TEXT NOT NULL REFERENCES payments(payment_id),
                from_state TEXT,
                to_state TEXT NOT NULL,
                bank_reference TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def save_payment(self, payment: Payment, previous_state: PaymentState | None = None, bank_reference: str | None = None) -> None:
        self.connection.execute(
            """INSERT INTO payments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(payment_id) DO UPDATE SET
                state=excluded.state, updated_at=excluded.updated_at,
                bank_authorization_id=excluded.bank_authorization_id,
                bank_capture_id=excluded.bank_capture_id,
                bank_void_id=excluded.bank_void_id,
                bank_refund_id=excluded.bank_refund_id""",
            (
                payment.payment_id,
                payment.order_id,
                payment.customer_id,
                payment.amount_cents,
                payment.currency,
                payment.state.value,
                payment.created_at,
                payment.updated_at,
                payment.bank_authorization_id,
                payment.bank_capture_id,
                payment.bank_void_id,
                payment.bank_refund_id,
            ),
        )
        if previous_state is not None:
            self.connection.execute(
                "INSERT INTO payment_events(payment_id, from_state, to_state, bank_reference, created_at) VALUES (?, ?, ?, ?, ?)",
                (payment.payment_id, previous_state.value, payment.state.value, bank_reference, payment.updated_at),
            )
        self.connection.commit()

    def get_payment(self, payment_id: str) -> Payment | None:
        row = self.connection.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,)).fetchone()
        return self._payment(row) if row else None

    def find_by_order(self, order_id: str) -> list[Payment]:
        rows = self.connection.execute("SELECT * FROM payments WHERE order_id = ? ORDER BY created_at", (order_id,)).fetchall()
        return [self._payment(row) for row in rows]

    def find_by_customer(self, customer_id: str) -> list[Payment]:
        rows = self.connection.execute("SELECT * FROM payments WHERE customer_id = ? ORDER BY created_at", (customer_id,)).fetchall()
        return [self._payment(row) for row in rows]

    def get_idempotency(self, operation: str, key: str) -> tuple[str, dict[str, Any] | None] | None:
        row = self.connection.execute(
            "SELECT fingerprint, response_json FROM idempotency_keys WHERE operation = ? AND key = ?",
            (operation, key),
        ).fetchone()
        if not row:
            return None
        return row["fingerprint"], json.loads(row["response_json"]) if row["response_json"] else None

    def save_idempotency(self, operation: str, key: str, fingerprint: str, response: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO idempotency_keys(operation, key, fingerprint, response_json) VALUES (?, ?, ?, ?)",
            (operation, key, fingerprint, json.dumps(response)),
        )
        self.connection.commit()

    @staticmethod
    def _payment(row: sqlite3.Row) -> Payment:
        return Payment(
            payment_id=row["payment_id"],
            order_id=row["order_id"],
            customer_id=row["customer_id"],
            amount_cents=row["amount_cents"],
            currency=row["currency"],
            state=PaymentState(row["state"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            bank_authorization_id=row["bank_authorization_id"],
            bank_capture_id=row["bank_capture_id"],
            bank_void_id=row["bank_void_id"],
            bank_refund_id=row["bank_refund_id"],
        )

