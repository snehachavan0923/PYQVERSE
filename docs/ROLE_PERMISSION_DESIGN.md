# Role and Permission Design

PYQVERSE has exactly two roles:

- `STUDENT`
- `ADMIN_FACULTY`

There is no separate Faculty role. Public registration must always assign `STUDENT`; privileged assignment requires an authorized administrative process. The first user must never become an administrator automatically.

Supabase Auth and FastAPI role enforcement are implemented. No insecure placeholder RLS policies are installed.

Phase 3 protects FastAPI business operations independently of Supabase Data API:

| Capability | STUDENT | ADMIN_FACULTY |
|---|---|---|
| Public registration | RVCE email only | Not public |
| Email verification | Required | Required |
| Login method | Email + password | Email + password |
| Student onboarding | Own account | No |
| Student dashboard | Own profile only | No |
| Admin dashboard | Forbidden | Yes |
| Role self-update | Forbidden | Forbidden |

The initial administrator is provisioned once with the backend-only `backend/scripts/provision_admin.py` command. A second administrator is refused, and rerunning the same administrator is reported as already provisioned.
