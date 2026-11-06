# Architecture

```text
FicMart order service
         |
         v
FastAPI routes -> Service (state + idempotency) -> BankClient -> mock bank
                         |
                         v
                   ReceiptRepository
                   (payments, events, keys)
```

## API layer

`api.py` owns HTTP concerns: request validation, required headers, status codes, and OpenAPI
documentation. It does not implement payment rules. `create_app` accepts an optional service,
so tests can inject a deterministic bank and in-memory receipt store.

## Service layer

`Service` coordinates one operation under an async lock per process. It checks the gateway
idempotency key and request fingerprint, validates state, calls the bank, then persists the
receipt and response. The bank is accessed through a protocol, which separates the gateway
from a particular HTTP client or test double.

## Receipt repository

SQLite stores three related records:

- `payments`: current source-of-truth receipt and bank references.
- `payment_events`: append-only state transition history.
- `idempotency_keys`: operation, key, request fingerprint, and replay response.

The repository is intentionally a small adapter. A PostgreSQL implementation can replace it
without changing state-machine or API code.

## Distributed failure boundary

The bank call happens before the final receipt update. If a process dies after the bank accepts
the request but before our write, a retry with the same gateway key produces the same bank
idempotency key. The bank replays its original result, allowing the service to complete the
receipt. A `pending` receipt makes this recovery state visible rather than pretending the
payment succeeded.

## Security boundary

Card data is accepted only for authorization and is never placed in the receipt, event log,
or idempotency response. In production, use tokenized payment methods and a PCI-compliant
provider; this sample exists to demonstrate coordination patterns, not card handling.

