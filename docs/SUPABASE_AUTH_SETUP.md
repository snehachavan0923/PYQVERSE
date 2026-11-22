# Supabase Auth and Email Setup

## Credentials

Configure server variables in `backend/.env`:

```text
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY=YOUR_SUPABASE_SERVICE_ROLE_KEY
FRONTEND_URL=http://localhost:5173
```

Configure public frontend variables in `frontend/.env`:

```text
VITE_SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
VITE_SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
```

Never place `SUPABASE_SERVICE_ROLE_KEY` in frontend configuration or Git. The PYQVERSE API uses the anon key for user authentication; privileged administrator provisioning remains a backend-only operation.

## Email/password authentication

1. Enable the Email provider in Supabase Auth.
2. Keep email confirmation enabled so students must verify their address through Supabase's confirmation link.
3. Public registration always creates `STUDENT` users and rejects non-`@rvce.edu.in` addresses.
4. Login uses Supabase `sign_in_with_password`. The backend verifies the returned access token with `auth.get_user` and rejects unverified or inactive accounts.
5. Configure the Supabase **Site URL** and permitted redirect URLs for your frontend. Password recovery links redirect to `FRONTEND_URL/reset-password`.

The frontend registration page asks for full name, email, password and password confirmation. After registration, students are told to open the confirmation link. They are not automatically authenticated while confirmation is pending.

### Confirmation email template and branding

In **Authentication → Email Templates → Confirm signup**, set the subject to **Confirm your PYQVERSE account** and use a confirmation link as the primary action. Keep `{{ .ConfirmationURL }}` in this template; do not replace the signup confirmation with an OTP code.

```html
<!doctype html>
<html lang="en">
	<head>
		<meta charset="utf-8">
		<meta name="viewport" content="width=device-width, initial-scale=1">
		<title>Confirm your PYQVERSE account</title>
	</head>
	<body style="margin:0;padding:24px;background:#f3f6fb;font-family:Arial,Helvetica,sans-serif;color:#172033;">
		<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e3e9f2;border-radius:12px;">
			<tr>
				<td style="padding:32px 32px 12px;text-align:center;">
					<div style="font-size:26px;font-weight:700;letter-spacing:1px;color:#2457c5;">PYQVERSE</div>
				</td>
			</tr>
			<tr>
				<td style="padding:8px 32px 32px;">
					<h1 style="margin:0 0 16px;font-size:22px;line-height:1.35;">Confirm your email</h1>
					<p style="margin:0 0 20px;font-size:15px;line-height:1.6;">
						Confirm your email address to finish creating your PYQVERSE student account.
					</p>
					<p style="margin:0 0 24px;text-align:center;">
						<a href="{{ .ConfirmationURL }}" style="display:inline-block;padding:13px 22px;background:#2457c5;border-radius:7px;color:#ffffff;text-decoration:none;font-size:15px;font-weight:700;">
							Confirm email
						</a>
					</p>
					<p style="margin:0;font-size:14px;line-height:1.6;color:#536078;">
						If you did not request a PYQVERSE account, you can ignore this message. Do not forward this email or share its confirmation link.
					</p>
				</td>
			</tr>
		</table>
	</body>
</html>
```

For password recovery, configure **Authentication → Email Templates → Reset Password** with a recovery link using Supabase's `{{ .ConfirmationURL }}` variable, and set the project **Site URL** and redirect allowlist to include the exact frontend reset URL. The backend requests redirects to `FRONTEND_URL/reset-password`.

To brand the sender, open **Authentication → SMTP Settings**, enable a custom SMTP provider, and set the sender display name to **PYQVERSE**. The sender display name does not change the sender email address. Supabase's default email service may restrict sender customization, recipients, and delivery; a verified custom SMTP provider/domain is required for reliable production delivery. Verify SPF/DKIM/DMARC with the provider. Do not commit or expose SMTP credentials, and do not claim the sender branding is live until a real email has been received and checked.

## Password recovery

The frontend requests recovery through the backend:

- `POST /api/v1/auth/password-reset/request`

The backend calls Supabase `reset_password_for_email` with a redirect to the frontend reset page. The reset page uses the Supabase JavaScript client to consume the recovery session and call `updateUser({ password })`. The response message is intentionally generic so account existence is not disclosed.

## Initial administrator provisioning

The previous public bootstrap endpoint and `ADMIN_BOOTSTRAP_TOKEN` have been removed.

Use the backend-only provisioning script:

```bash
cd backend
source .venv/bin/activate
python scripts/provision_admin.py
```

You can supply non-secret values through the environment:

```bash
ADMIN_EMAIL=you@example.com ADMIN_FULL_NAME="Your Name" python scripts/provision_admin.py
```

The password is read from `ADMIN_PASSWORD` if set, otherwise from a secure `getpass` prompt. The script:

- Creates or updates the Supabase Auth user with the password flow.
- Creates or updates the linked PYQVERSE `users` row.
- Assigns `ADMIN_FACULTY` through the trusted backend process.
- Verifies the role and Supabase/application ID link.
- Refuses to create a second administrator.
- Is safe to rerun for the same administrator email and reports `already_provisioned`.

Do not put the administrator password in `.env`, source code, seed files, Git, logs or documentation.

## Numeric OTP (deferred)

Numeric OTP is not part of the current login or registration journey. Do not configure the login UI to depend on OTP. The Supabase Auth client, backend JWT verification and role enforcement remain in place so numeric OTP can be added later as an additional Supabase-backed flow.

If OTP is reintroduced:

- Use Supabase's real OTP verification only.
- Do not generate local codes or fake verification.
- Do not automatically authenticate unverified users.
- Keep email confirmation behavior unless the security policy is deliberately changed.

## Sender branding

For the sender-name dashboard steps and the PYQVERSE confirmation template, see **Confirmation email template and branding** above. Configure custom SMTP and a verified sending domain for production, then verify SPF/DKIM/DMARC. Do not commit SMTP credentials. Supabase's default email service may restrict recipients and apply rate limits.
