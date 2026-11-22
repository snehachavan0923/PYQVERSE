# Authentication Architecture

PYQVERSE uses official Supabase Auth through the Supabase Python and JavaScript libraries.

- Public student registration creates only `STUDENT` users.
- Student email addresses must end exactly with `@rvce.edu.in`.
- Student registration and login use Supabase email/password authentication.
- Student registration uses Supabase's confirmation-link email flow. Unconfirmed users cannot use protected APIs.
- Administrator accounts may use personal or institutional email addresses.
- Exactly one initial `ADMIN_FACULTY` account is created through the trusted backend provisioning script.
- FastAPI verifies Supabase access tokens by calling `auth.get_user`.
- FastAPI synchronizes verified identities into PostgreSQL and enforces roles.
- Service-role credentials remain server-side only and are never exposed to the frontend.
- Public registration cannot create an administrator and cannot select a role.

## Password authentication

- Registration requires full name, email, password and password confirmation.
- Passwords must be at least 8 characters and contain uppercase, lowercase and numeric characters.
- Login calls Supabase `sign_in_with_password`.
- Sessions are persisted by the frontend and verified by the backend on every protected request.
- Password recovery uses Supabase's supported `reset_password_for_email` flow and the frontend `updateUser` recovery session.

## Administrator provisioning

The public bootstrap endpoint has been removed. Use the backend-only script:

```bash
cd backend
source .venv/bin/activate
python scripts/provision_admin.py
```

The script accepts `ADMIN_EMAIL` and `ADMIN_FULL_NAME` from the environment or prompts interactively. The password is read from `ADMIN_PASSWORD` or a secure `getpass` prompt. It is never written to the database, source, seed files, Git or logs.

The script uses the Supabase service-role key to create or update the Auth identity, links the Supabase user ID to the application `users` row, assigns `ADMIN_FACULTY`, verifies the role, and refuses to create a second administrator. Re-running with the same administrator email is safe and reports `already_provisioned`.

## Numeric OTP (deferred)

Numeric OTP login was removed from the normal authentication journey. The current architecture intentionally keeps Supabase Auth, session handling, backend JWT verification and role enforcement in place so numeric OTP can be reintroduced later without rebuilding authentication.

If OTP is reintroduced, add it as an additional Supabase-backed factor or flow; do not create locally generated codes, fake verification or automatic authentication of unverified users.

## Development Email Delivery

Custom SMTP is intentionally deferred until deployment. During development, use only email addresses permitted by the Supabase project settings. Supabase default email limits apply, and actual delivery testing remains pending until custom SMTP and a verified sending domain are configured.
