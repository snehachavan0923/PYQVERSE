# Backend Architecture

- `app/core/config.py`: environment loading and validation.
- `app/database/connection.py`: SQLAlchemy engine, sessions and health check.
- `app/database/base.py`: SQLAlchemy declarative base.
- `app/models/`: normalized academic, document, progress and AI metadata models.
- `app/schemas/`: Pydantic API response models.
- `app/api/routes.py`: system and academic endpoints.
- `app/services/`: repeatable data services and seed logic.
- `alembic/`: versioned database migrations.
- `tests/`: environment, database and API tests.

Database sessions are created per request and always closed. SQLAlchemy parameterized statements are used for data access.
