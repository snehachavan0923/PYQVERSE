# Academic Data Structure — Phase 6.0

## Reusable hierarchy

`College -> AcademicScheme -> Semester -> Subject -> Unit -> Topic -> Subtopic`

- `AcademicScheme` remains college-scoped and now supports optional validity dates.
- `Branch` represents a program. `BranchSubjectOffering` associates a subject with one or more branches without duplicating subject records.
- `Subject` remains unique by scheme and course code. It carries course category, delivery mode, L:T:P credits, pedagogical hours, and source provenance.
- `ElectiveBasket` and `ElectiveOption` remain the elective grouping mechanism; baskets may be scheme-wide or branch-specific.
- `SyllabusVersion` remains the subject-specific version boundary. Imported versions stay inactive and `DRAFT`.
- Unit order is unique within a version; legacy unversioned units retain subject-scoped ordering. Topic and subtopic order is unique within their parent.
- Source verification (`VERIFIED`, `NEEDS_REVIEW`, `NOT_AVAILABLE`) is distinct from the existing publication lifecycle (`DRAFT`, `PENDING`, `VERIFIED`, `REJECTED`).
- Source page references are physical PDF page numbers. The checked-in source is `docs/source-syllabus/Syllabus_Copy.pdf`; its SHA-256 is recorded alongside the data. Printed syllabus page numbers are documented separately.

## Semester III CSE catalog

Source: `docs/source-syllabus/Syllabus_Copy.pdf`, RVCE 2025 Scheme (77 physical PDF pages). The Semester III index/catalog is on physical PDF page 1. Course page references below show physical PDF pages, followed by the printed syllabus page numbers.

| Code | Official title | Source category / delivery | L:T:P | Credits | Pedagogical hours L:T:P:S | Physical PDF pages | Source status |
|---|---|---|---:|---:|---:|---:|---|
| MA231TC | Linear Algebra and Probability Theory | Professional Core Course / Theory | 3:1:0 | 4 | 45:30:0:45 | 5–6 (1–2) | VERIFIED |
| CV232TA | Environment and Sustainability | Professional Core Course / Theory | 3:0:0 | 3 | 45:0:0:45 | 7–9 (3–5) | VERIFIED |
| ME232TB | Material Science for Engineers | Professional Core Course / Theory | 3:0:0 | 3 | 45:0:0:45 | 10–11 (6–7) | VERIFIED |
| BT232TD | Bioinspired Engineering | Professional Core Course / Theory | 3:0:0 | 3 | 45:0:0:45 | 12–14 (8–10) | VERIFIED |
| CS233AI | Data Structures and Applications | Professional Core Course / Theory & Practical | 3:0:1 | 4 | 45:0:30:45 | 15–19 (11–15) | VERIFIED |
| CS234AI | Applied Digital Logic Design and Computer Organization | Professional Core Course / Theory & Practical | 3:0:1 | 4 | 45:0:30:45 | 20–22 (16–18) | VERIFIED |
| CS235AT | Operating Systems | Professional Core Course / Theory | 3:0:0 | 3 | 45:0:0:45 | 23–24 (19–20) | VERIFIED |
| CS236AT | Quantum Computing Essentials | Professional Core Course / Theory | 3:0:0 | 3 | 45:0:0:45 | 25–27 (21–23) | VERIFIED |
| CS238DL | Applied Design Thinking Lab | Professional Core Course / Practical | 0:0:1 | 1 | 0:0:30:0 | 28–29 (24–25) | VERIFIED |
| MAT149AT | Bridge Course Mathematics | Bridge Course / Theory | 2:0:0 | 0 audit in index; course page states 2 | 30:0:0:30 | 30 (26) | NEEDS_REVIEW |

CV232TA, ME232TB and BT232TD are alternatives in the shared Semester III course row, not three mandatory courses. They are represented as separate subject records in one branch-specific elective basket. Their source category remains Professional Core Course; the elective basket represents the selection rule.

The index total is 22 credits when exactly one 3-credit alternative is selected; the MAT149AT audit row contributes zero to that total even though its course page states 2 credits. Its L:T:P allocation is retained separately and the credit conflict remains flagged for review.

The source-backed import contains 43 units, 74 topics and 453 subtopics across the 10 subjects. Per-subject counts:

| Code | Units | Topics | Subtopics |
|---|---:|---:|---:|
| MA231TC | 5 | 5 | 44 |
| CV232TA | 5 | 5 | 49 |
| ME232TB | 5 | 11 | 61 |
| BT232TD | 5 | 6 | 50 |
| CS233AI | 5 | 14 | 77 |
| CS234AI | 5 | 11 | 64 |
| CS235AT | 5 | 9 | 46 |
| CS236AT | 5 | 7 | 39 |
| CS238DL | 0 | 0 | 0 |
| MAT149AT | 3 | 6 | 23 |

Five-unit theory courses have 9-hour units; MAT149AT has three 10-hour units. CS238DL has no numbered units in the source; its lab instructions and assessment are retained as practical-component content, not fabricated as theory units. The previously empty topic outlines for MA231TC, CV232TA, ME232TB, BT232TD, CS236AT and MAT149AT have been transcribed at topic/subtopic level. The five CS233AI self-learning sections now carry the actual listed extended topics, rather than a placeholder standing alone.

The source omits the explicit “Unit IV” label before Trees in CS233AI and before Basic Structure of Computers in CS234AI. The source content is retained under the inferred fourth unit, and those unit boundaries remain `NEEDS_REVIEW`; no source verification is inferred for the missing labels. MAT149AT also remains `NEEDS_REVIEW`: the Semester III index marks it `0*` (Audit), while its course page states total credits `2`. Other subject records are source-verified against the PDF. Verification tests check transcription coverage and provenance, but do not themselves confer source verification.

Source page fields refer to physical PDF pages (e.g. MA231TC pages 5–6); the parenthesized values in the table are the printed syllabus pages. The PDF SHA-256 is `d93909e57ca46c73fe5b62df0b2669c1ac84a0ab4f00b76f6fe5db8bc064e29c`.

## Future import candidate — Semester IV only

These are index entries from the same PDF, not imported or published syllabus records:

- CS241AT — Discrete Mathematical Structures and Combinatorics
- CV232TA / ME232TB / BT232TD — Environment and Sustainability / Material Science for Engineers / Bioinspired Engineering (shared alternatives)
- CD343AI — Design and Analysis of Algorithms
- CS345AI — Embedded Systems, Iot and Edge Ai
- CS246AT — Computer Networks
- CS248ATX — Professional Electives
- CS139AT — Bridge Course C Programming
- HS248LX — AE Course

No syllabus content is imported for Semesters I, II, V, VI, VII or VIII.

## Import and publication safeguards

`app.data.semester_iii_2025` contains catalog metadata separate from application logic. The source-verified outline is versioned as `2025-semester-iii-source-v2`; the earlier v1 version and its content are not updated or deleted. The seed uses deterministic identifiers and natural-key constraints, creates missing rows, enriches only empty subject metadata fields, and reports conflicts instead of replacing mismatched records. It never removes existing rows.

Run the module without `--apply` for a static plan; this does not connect to the database. `--apply` is required to write records. The Phase 6 import was not run against the configured database. Imported syllabus versions, units, topics and subtopics default to inactive `DRAFT`, regardless of source verification status.

## API and frontend preparation

- Public catalog endpoints continue to support the existing onboarding/catalog views.
- Unit, topic and subtopic reads require a student role, a matching scheme/semester enrollment, a branch offering, and active/published/verified source records.
- Admin academic endpoints retain existing scheme, semester, subject and elective management; they now also manage branch-subject offerings and expose metadata/provenance.
- Frontend follow-up should reuse `Onboarding`, `StudentSubjects`, `StudentSubjectDetail`, and `AdminAcademic` plus existing layout and design tokens. Add scheme/semester filtering to onboarding and subject listing, then unit/topic navigation to subject detail; no dashboard redesign is required in this phase.

## Migration baseline note

The configured database previously reported Alembic revision `b6d2f8a1c947`. Git history contains `b6d2f8a1c947_phase_6_learning.py` on `backup-before-main-cleanup`; it is a sibling of the academic migration `6f8a2c9d1b40`, and both declare `a4e1c3d7f902` as parent. The current migration graph includes only the academic branch. Reconcile the deployed schema and migration graph before applying anything; do not stamp, reset, upgrade, or edit the live database as part of this import.
