# P4 Production Readiness Notes

P4 adds the first production-readiness layer for the ecommerce dispute evidence pack assistant.

## Runtime protections

- `OCR_REQUIRE_REAL=1`: fail the Case if real OCR is not configured or did not run.
- `OCR_MIN_TEXT_CHARS=80`: fail or warn when OCR text is too short to support reliable analysis.
- `PRIVACY_REDACTION_ENABLED=1`: redact sensitive values before they are stored or shown in logs.
- `/api/runtime`: inspect non-secret runtime status, including OCR mode, storage driver, privacy redaction, observability, and OpenAI configuration.

## Sensitive data redaction

The system redacts these values in Case results, OCR results, AI logs, system logs, Trace output, and observability events:

- phone numbers
- ID card numbers
- email addresses
- order IDs
- tracking numbers
- address-like text
- raw binary payloads

## Storage adapter

The current P4 build still uses the JSON file store through `CASE_STORE_DRIVER=json`.

`storage_adapter.py` is now the storage boundary. A future database adapter can replace the JSON driver without rewriting Case workflow logic.

Recommended future drivers:

- Supabase / Postgres
- Vercel KV
- SQLite for single-machine deployment

## Recommended production environment

```text
OCR_PROVIDER=external
OCR_API_URL=https://your-ocr-service.example.com/ocr
OCR_REQUIRE_REAL=1
OCR_MIN_TEXT_CHARS=80
PRIVACY_REDACTION_ENABLED=1
ADMIN_TOKEN=replace_with_private_admin_token
CASE_STORE_DRIVER=json
OBSERVABILITY_ENABLED=1
```

For long-term online usage, do not rely on the default JSON file store on Vercel because serverless file storage is ephemeral.
