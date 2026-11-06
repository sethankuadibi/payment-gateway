# Engineering trade-offs

## Architecture

FastAPI keeps the HTTP contract explicit and gives FicMart an interactive OpenAPI document.
The domain service is framework-independent, while the repository and bank client are replaceable
adapters. This is more structure than a single script, but payment correctness benefits from
clear boundaries.

## State management

The gateway is the source of truth for its receipts and stores a transition event for each
successful operation. SQLite makes the project runnable with one command and gives durable
local behavior. Production would use PostgreSQL with transactions, connection pooling, and
row-level locking.

## Failure handling

The bank client retries only transient failures and always reuses the same bank idempotency
key. A request that fails after a bank-side success can therefore be retried safely. The sample
uses an in-process lock to serialize operations; a multi-replica deployment needs database
locks or a distributed idempotency coordinator.

## Idempotency

Gateway responses are stored by operation and key, with a SHA-256 request fingerprint. This
protects against duplicate charges and detects accidental key reuse. In-flight keys are not
marked complete until the receipt is persisted, so a crash leaves a visible `pending` state
and a safe recovery path.

## What I would change in production

- Use tokenized payment methods and a PCI-compliant provider.
- Replace SQLite with PostgreSQL and use transactional outbox/reconciliation workers.
- Add authentication, authorization, request rate limits, structured redacted logs, metrics,
  tracing, and alerting.
- Make idempotency records durable across replicas and add a scheduled bank reconciliation job.
- Add a dead-letter workflow for operations that remain uncertain after repeated retries.

