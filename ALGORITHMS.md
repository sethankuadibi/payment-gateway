# Algorithms

## State transition validation

Each payment state maps to a finite set of allowed targets:

```text
pending    -> authorized
authorized -> captured | voided
captured   -> refunded
voided     -> none
refunded   -> none
```

The service validates this table before calling the bank. Invalid requests are rejected with
no external side effect. A transition is `O(1)`.

## Idempotency and request fingerprints

An idempotency record is addressed by `(operation, key)`. The gateway hashes a canonical JSON
representation of the request. A matching fingerprint returns the stored response; a different
fingerprint returns a conflict because silently changing a payment request is unsafe.

Hashing is `O(p)` for payload size `p`; indexed lookup is average `O(1)`.

## Retry safety

The HTTP bank client retries timeouts, network failures, and 5xx responses with exponential
backoff plus jitter. It sends the same `Idempotency-Key` on every attempt. Permanent 4xx errors
stop immediately. The bank, not the gateway, deduplicates repeated external requests.

## Recovery after partial failure

An authorization receipt is inserted as `pending` before the bank call. A successful bank
response transitions it to `authorized` and stores the bank reference. If the call fails,
the receipt remains `pending`; a caller can retry with the same key and the bank can replay a
previous success. The design makes uncertainty explicit instead of marking a failed call as
declined.

## Query indexes

Receipts are indexed by `order_id` and `customer_id`, so lookup is `O(log n + k)` in SQLite,
where `n` is receipt count and `k` is the number of matching records. State history is append
only and ordered by its auto-increment event ID.

