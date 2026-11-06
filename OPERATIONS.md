# Operations runbook

The gateway listens on port `8000`, stores receipts in the configured database, and calls the
bank through `BANK_URL`. The `/health` endpoint is a liveness check.

## Local stack

```bash
make up
curl --fail http://localhost:8000/health
make logs
make down
```

The Compose stack persists SQLite under a named volume. The gateway runs as UID/GID `10001`
with a read-only root filesystem and no Linux capabilities.

## Production checklist

- Replace SQLite with PostgreSQL and enable connection pooling.
- Put the API behind TLS, authentication, authorization, and request rate limits.
- Use tokenized payment methods; never log or persist raw card data.
- Add metrics for bank latency, retries, pending receipts, and state-transition errors.
- Run reconciliation against bank records for payments left pending after a timeout.
- Back up the receipts database and test restore procedures.

## Incident response

1. Check `/health` and service logs.
2. If the bank is degraded, stop retries from amplifying load and preserve pending receipts.
3. Restart only after confirming the database volume is mounted.
4. Re-run the original operation with its same idempotency key to recover an uncertain call.

