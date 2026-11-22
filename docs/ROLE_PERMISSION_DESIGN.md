# Role and Permission Design

PYQVERSE has exactly two roles:

- `STUDENT`
- `ADMIN_FACULTY`

There is no separate Faculty role. Public registration must always assign `STUDENT`; privileged assignment requires an authorized administrative process. The first user must never become an administrator automatically.

Authentication and RLS will be implemented in a later phase. No insecure placeholder RLS policies are currently installed.
