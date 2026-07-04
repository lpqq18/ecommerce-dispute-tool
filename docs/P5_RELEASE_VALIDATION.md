# P5 Release Validation

P5 is the release validation stage. It should not introduce major product behavior changes. Its job is to prove the current build is safe enough for a real deployment test.

## What P5 checks

- required source files exist
- deployment bundle contains required files
- Vercel config points to `npm run build` and `dist`
- API responses are marked `Cache-Control: no-store`
- privacy redaction is enabled
- runtime config does not expose secrets
- hardcoded secret scan passes
- real OCR enforcement is visible
- real screenshot regression samples are present or explicitly skipped

## Commands

```powershell
node scripts/build.js
python scripts/p4_smoke_test.py
python scripts/p5_release_check.py
```

In Codex runtime, use the bundled Python and Node paths if local commands are unavailable.

## Real screenshot regression

Place real ecommerce screenshots under:

```text
test_samples/real_cases
```

Recommended groups:

- chat screenshots
- order detail screenshots
- logistics screenshots
- refund/after-sales screenshots
- bad review screenshots

P5 does not require real samples to exist before the release checklist can run, but it will mark the item as `skip`. Before a public beta, this skip should be closed.

## Production environment recommendation

```text
OCR_PROVIDER=external
OCR_API_URL=https://your-ocr-service.example.com/ocr
OCR_REQUIRE_REAL=1
OCR_MIN_TEXT_CHARS=80
PRIVACY_REDACTION_ENABLED=1
ADMIN_TOKEN=replace_with_private_admin_token
OBSERVABILITY_ENABLED=1
```

## Release decision rule

- Blocker count must be `0`.
- Warnings are acceptable for local development.
- For public beta, close these warnings:
  - `ADMIN_TOKEN` not configured
  - real OCR provider not configured
  - `OCR_REQUIRE_REAL` not enabled
  - real screenshot samples skipped
  - JSON store used for long-term online storage
