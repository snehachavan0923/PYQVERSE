# Data Import Guide

The Phase 6 importer is scoped to Semester III CSE metadata and the syllabus outline verified against `docs/source-syllabus/Syllabus_Copy.pdf` (RVCE 2025 Scheme). Its SHA-256 is pinned in `app.data.semester_iii_2025`. It creates records only when absent, fills only empty subject metadata fields, preserves manually maintained values and prior syllabus versions, and reports conflicts.

The default command validates and prints a static plan without connecting to the database:

```bash
cd backend
.venv/bin/python -m app.services.seed_academic_catalog
```

Writing records requires the explicit `--apply` flag:

```bash
.venv/bin/python -m app.services.seed_academic_catalog --apply
```

Do not use `--apply` against a production database without approval. Imported syllabus versions and hierarchy records remain inactive and in `DRAFT`; source verification does not publish content. The importer stores the course outline as ordered units, topics and subtopics; source page references use physical PDF pages. It retains practical instructions in the course practical-component field where the source does not define numbered theory units. See [ACADEMIC_DATA_STRUCTURE.md](./ACADEMIC_DATA_STRUCTURE.md) for source references, known ambiguities, counts, and future-semester boundaries.

Do not import fake units, topics, students, question papers or unverified syllabus material.
