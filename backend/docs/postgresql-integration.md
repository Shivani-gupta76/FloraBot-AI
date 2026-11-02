# PostgreSQL integration checks

The regular test suite overrides the application database dependency with isolated SQLite. It does not test PostgreSQL row locks or concurrency. The opt-in tests in `tests/integration/test_postgres_backend.py` use a separate PostgreSQL database and do not read `DATABASE_URL` or `.env`.

## Prepare an isolated test database

Create a disposable database specifically for integration tests (for example `florabot_test`) using your database administrator's normal provisioning process. Do not point this variable at the development database. The test harness rejects non-PostgreSQL URLs and database names that do not end in `_test`.

Set the URL in the current PowerShell process only, using the disposable database's credentials:

```powershell
$env:FLORABOT_TEST_DATABASE_URL = 'postgresql+psycopg://<test-user>:<test-password>@<host>:<port>/florabot_test'
.\.venv\Scripts\python.exe -m pytest tests\integration -q
```

Do not print the variable or place credentials in source control, command transcripts, screenshots, or chat. The test fixture creates a uniquely named schema in that dedicated test database and leaves it in place; it does not drop schemas, tables, or records. Dispose of the dedicated test database using its normal isolated lifecycle after tests.

## Covered checks

- PostgreSQL foreign-key enforcement and constraint rollback.
- Concurrent creation using one device idempotency key; exactly one row is persisted and both callers receive its identity.
- Concurrent device polling; a single pending command is claimed by one poller using row locking and `SKIP LOCKED`.
- Disease detection plus alert transaction persistence and associated LED2 command persistence.
- Failure rollback leaves no partially persisted detection row.

If `FLORABOT_TEST_DATABASE_URL` is absent, these tests are skipped. SQLite success must not be described as PostgreSQL concurrency verification.
