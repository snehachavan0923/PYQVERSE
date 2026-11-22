# Role and Permission Design

PYQVERSE has exactly two roles:

- `STUDENT`
- `ADMIN_FACULTY`

There is no separate Faculty role. Public registration must always assign `STUDENT`; privileged assignment requires an authorized administrative process. The first user must never become an administrator automatically.

Authentication and RLS will be implemented in a later phase. No insecure placeholder RLS policies are currently installed.

Phase 3 protects FastAPI business operations independently of Supabase Data API:

| Capability | STUDENT | ADMIN_FACULTY |
|---|---|---|
| Public registration | RVCE email only | Not public |
| Email verification | Required | Required |
| Student onboarding | Own account | No |
| Student dashboard | Own profile only | No |
| Admin dashboard | Forbidden | Yes |
| Role self-update | Forbidden | Forbidden |

The initial administrator is configured once with `ADMIN_BOOTSTRAP_TOKEN`. Subsequent bootstrap attempts are rejected.
