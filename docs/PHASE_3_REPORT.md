# Phase 3 Report

## Implemented

- Supabase-backed student registration using full name, `@rvce.edu.in` email, password and password confirmation.
- Public registration assigns `STUDENT` only; no public role selector or admin registration endpoint exists.
- Supabase signup email confirmation remains enabled and uses the confirmation-link template.
- Email/password login uses Supabase `sign_in_with_password` for both supported roles.
- Backend validates Supabase access tokens with `auth.get_user`, synchronizes the Supabase identity, and enforces database-backed roles and account status.
- Frontend sessions are persisted and revalidated/refreshed through the backend on page startup.
- Logout and Supabase password recovery are implemented.
- Initial `ADMIN_FACULTY` provisioning is restricted to the backend-only `scripts/provision_admin.py` command.
- Student onboarding and existing role-gated academic/profile pages are present in the current worktree.
- Numeric OTP login is deferred and removed from the normal authentication journey.

## Administrator provisioning

Run the command from `backend/` with the backend virtual environment activated:

```bash
python scripts/provision_admin.py
```

The operator supplies the administrator email and name interactively or via non-secret environment variables. The password is requested through a hidden prompt (or may be supplied through a secure local environment variable). The script uses the backend-only service-role key, links the Supabase identity to the application user record, assigns and verifies `ADMIN_FACULTY`, and prevents an accidental second administrator. It never writes the plaintext password to PostgreSQL or logs.

## Database and migrations

The existing Phase 3 migration is `1a7d8c2f4e91_phase_3_auth_onboarding.py`. The database reported revision `1a7d8c2f4e91` as current, matching the single Alembic head. The read-only `alembic check` reported no new upgrade operations. No migration or destructive database operation was run during this audit.

## Validation from the Phase 3 audit

- Backend test suite: **42 passed**, with one existing Starlette/httpx deprecation warning.
- Python compilation: passed for `app`, `scripts` and `tests`.
- Alembic head/current check and schema drift check: passed; database remains at the Phase 3 head.
- Dependency check: `pip check` reported no broken requirements after aligning Supabase transitive constraints.
- Frontend lint: completed with one `react(only-export-components)` warning in `AuthContext.tsx`.
- Frontend production build: passed; Vite reported the existing large-chunk advisory.
- Frontend test script: not configured, so no frontend tests were available.
- No real Supabase authentication, password-reset email or confirmation email was sent during automated validation.

## Manual Supabase setup and end-to-end testing

Enable the Email provider and email confirmation, configure the Confirm signup template to use `{{ .ConfirmationURL }}`, set the Site URL and allow the frontend confirmation/recovery redirects. For production sender branding and reliable delivery, configure custom SMTP and a verified sending domain. See [SUPABASE_AUTH_SETUP.md](SUPABASE_AUTH_SETUP.md).

The backend environment values and database migration are configured locally, but Supabase sign-in, email confirmation, recovery delivery and the administrator's first login were not live-tested during this audit. Phase 3 is ready for manual end-to-end testing once the required Supabase dashboard email and redirect settings are confirmed.

No Phase 4 upload, OCR, PYQ-processing, AI, quiz or learning-resource workflows were implemented during this audit. Existing dashboard-related changes already present in the worktree were left untouched.