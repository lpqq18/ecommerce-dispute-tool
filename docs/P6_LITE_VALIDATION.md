# P6-lite Validation

P6-lite is a lightweight release validation stage for the current MVP when real OCR credentials and real ecommerce screenshots are not ready yet.

## Scope

P6-lite validates:

- Git repository and remote origin are configured.
- Current branch is expected to be `main`.
- Release bundle exists and includes required runtime files.
- Privacy redaction is enabled.
- Runtime config does not expose secrets.
- Known missing production items are recorded as follow-ups.

P6-lite does not validate:

- real OCR accuracy
- real ecommerce screenshot parsing
- Vercel production environment variables
- WeChat/mobile network behavior
- long-term production storage

## Command

```powershell
python scripts/p6_lite_check.py
```

Run after:

```powershell
node scripts/build.js
python scripts/p4_smoke_test.py
python scripts/p5_release_check.py
```

## Follow-ups Before Public Beta

- Configure `OCR_PROVIDER=external` and `OCR_API_URL`.
- Set `OCR_REQUIRE_REAL=1`.
- Set `OCR_MIN_TEXT_CHARS`.
- Configure `ADMIN_TOKEN`.
- Add real samples under `test_samples/real_cases`.
- Run real screenshot regression.
- Commit and push all changes to GitHub.
- Wait for Vercel deployment and verify the public URL.
- Verify WeChat access from a phone.
