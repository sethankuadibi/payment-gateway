# FicMart payment gateway

A resilient payment gateway API that sits between an e-commerce order service and a banking
partner. It owns the payment receipt, enforces a strict lifecycle, and makes every operation
safe to retry.

> This is an educational gateway. It never stores raw card details after an authorization
> request and should not be used for real payments.

## What it demonstrates

- Explicit payment state machine: `pending → authorized → captured → refunded`, with a
  separate `authorized → voided` branch.
- Gateway-level idempotency with request fingerprints and replayed responses.
- Bank-level idempotency keys that make transient retries safe.
- SQLite receipts and transition history for durable local development.
- HTTP error mapping that returns client-safe messages instead of stack traces.
- Contract-based bank client so real HTTP calls and deterministic test doubles share an API.

See [ARCHITECTURE.md](ARCHITECTURE.md), [ALGORITHMS.md](ALGORITHMS.md), and
[TRADEOFFS.md](TRADEOFFS.md) for the design reasoning.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
uvicorn payment_gateway.api:app --reload
```

The API runs at <http://localhost:8000>. Interactive docs are at
<http://localhost:8000/docs>.

By default it expects the mock bank at `http://localhost:8787` and stores receipts in
`gateway.sqlite3`. Configure `BANK_URL` and `DATABASE_URL` for another environment.

## Example request

```bash
curl -X POST http://localhost:8000/payments/authorize \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: order-123-authorize' \
  -d '{
    "order_id": "order-123",
    "customer_id": "customer-456",
    "amount_cents": 5000,
    "card": {"number": "4111111111111111", "cvv": "123", "expiry": "12/2030"}
  }'
```

Use the returned `payment_id` for `/capture`, `/void`, and `/refund`. Repeat a request with
the same idempotency key to receive the original response without a second bank operation.

## API surface

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/payments/authorize` | Create a receipt and reserve funds |
| `POST` | `/payments/{id}/capture` | Charge an authorized payment |
| `POST` | `/payments/{id}/void` | Release an authorization |
| `POST` | `/payments/{id}/refund` | Refund a captured payment |
| `GET` | `/payments/{id}` | Read a receipt |
| `GET` | `/orders/{id}/payments` | Find receipts for an order |
| `GET` | `/customers/{id}/payments` | Find a customer's history |
| `GET` | `/health` | Liveness check |

All mutating endpoints require an `Idempotency-Key` header.

## Development

```bash
make install
make check
```

The test suite uses deterministic bank fakes and never charges a real card or calls the mock
bank. See [OPERATIONS.md](OPERATIONS.md) for container deployment and production concerns.

