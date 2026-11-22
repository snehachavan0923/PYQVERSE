# API Documentation

System endpoints:

- `GET /`
- `GET /health`

Academic catalog endpoints:

- `GET /api/v1/academic/branches`
- `GET /api/v1/academic/schemes`
- `GET /api/v1/academic/semesters`
- `GET /api/v1/subjects`
- `GET /api/v1/subjects/{subject_id}`
- `GET /api/v1/subjects/{subject_id}/units`
- `GET /api/v1/units/{unit_id}/topics`

Authentication endpoints:

- `POST /api/v1/auth/register` — student-only email/password registration
- `POST /api/v1/auth/login` — email/password login
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/password-reset/request`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/student/onboarding`

Student endpoints (require a valid STUDENT session):

- `GET /api/v1/auth/student/dashboard`
- `GET /api/v1/auth/student/subjects`
- `GET /api/v1/auth/student/syllabus`
- `GET /api/v1/auth/student/pyqs`
- `GET /api/v1/auth/student/resources`
- `GET /api/v1/auth/student/profile`

Administrator/faculty endpoints (require a valid ADMIN_FACULTY session):

- `GET /api/v1/auth/admin/dashboard`
- `GET /api/v1/auth/admin/academic/branches`
- `GET /api/v1/auth/admin/academic/schemes`
- `GET /api/v1/auth/admin/academic/semesters`
- `GET /api/v1/auth/admin/academic/subjects`
- `GET /api/v1/auth/admin/academic/elective-options`
- `GET /api/v1/auth/admin/users?page=1&page_size=20&role=STUDENT&search=`
- `GET /api/v1/auth/admin/users/{user_id}`
- `GET /api/v1/auth/admin/profile`

The OpenAPI documentation is available at `/docs` while the backend is running.
