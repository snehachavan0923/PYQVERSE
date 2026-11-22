# Data Import Guide

The provided Semester III catalog can be reseeded safely:

```bash
cd backend
.venv/bin/python -m app.services.seed_academic_catalog
```

The seed reports inserted, updated and skipped records and preserves existing data.

Do not import fake units, topics, students, question papers or syllabus content. Future syllabus and document uploads require verified source data and authorization.
