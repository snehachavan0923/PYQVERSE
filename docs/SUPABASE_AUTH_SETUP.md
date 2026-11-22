# Supabase Auth Setup

Configure server variables in `backend/.env`:

```text
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY=YOUR_SUPABASE_SERVICE_ROLE_KEY
ADMIN_BOOTSTRAP_TOKEN=replace_with_a_random_one_time_secret
```

Configure public frontend variables in `frontend/.env`:

```text
VITE_SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
VITE_SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
```

Do not place `SUPABASE_SERVICE_ROLE_KEY` or `ADMIN_BOOTSTRAP_TOKEN` in frontend configuration or Git.

In Supabase:

1. Enable Email provider.
2. Enable Email OTP.
3. Configure permitted development test addresses while default email limits remain active.
4. Add `http://localhost:5173` as a redirect URL if redirects are used.
5. Configure custom SMTP and a verified sending domain before production.
6. Customize the Email OTP template to expose the OTP token required by the application.

Until custom SMTP is configured, email delivery testing is pending.
