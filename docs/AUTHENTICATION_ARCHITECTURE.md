# Authentication Architecture

PYQVERSE uses official Supabase Auth through the Supabase Python and JavaScript libraries.

- Public student registration can create only `STUDENT` users.
- Student email addresses must end exactly with `@rvce.edu.in`.
- Administrator accounts may use personal or institutional email addresses.
- Supabase delivers and verifies real email OTP values.
- FastAPI verifies Supabase access tokens by calling `auth.get_user`.
- FastAPI synchronizes verified identities into PostgreSQL and enforces roles.
- Service-role credentials, if supplied, remain server-side only.
- The initial administrator requires `ADMIN_BOOTSTRAP_TOKEN` and cannot be created by public registration.

## Development Email Delivery

Custom SMTP is intentionally deferred until deployment. During development, use only email addresses permitted by the Supabase project settings. Supabase default email limits apply, and actual delivery testing remains pending until custom SMTP and a verified sending domain are configured.
