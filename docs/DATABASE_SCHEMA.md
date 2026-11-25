# Database Schema

Academic catalog and offerings:

`colleges -> academic_schemes -> semesters -> subjects`

`colleges -> branches -> branch_subject_offerings -> subjects`

- A scheme is scoped to a college and may have validity dates.
- A subject is unique by scheme and course code; offerings associate it with one or more branches.
- Semester numbers are constrained to I–VIII and unique within a scheme.
- Elective baskets may be general to a scheme/semester or scoped to a branch; options reference existing subjects.

Learning hierarchy:

`subjects -> syllabus_versions -> units -> topics -> subtopics`

- Syllabus versions carry publication lifecycle, source document/page range, source verification status and whether source prose was imported.
- Unit ordering is scoped to a syllabus version. Legacy units without a version retain subject-scoped order constraints.
- Topics distinguish syllabus content, self-learning topics and practical content. Topic and subtopic order is unique within each parent.
- Source verification (`VERIFIED`, `NEEDS_REVIEW`, `NOT_AVAILABLE`) is distinct from content publication (`DRAFT`, `PENDING`, `VERIFIED`, `REJECTED`).

Student and academic tables:

- `users`, `student_profiles`, `student_subject_enrollments`
- `colleges`, `branches`, `academic_schemes`, `semesters`, `subjects`
- `branch_subject_offerings`, `elective_baskets`, `elective_options`
- `syllabus_versions`, `syllabus_documents`, `units`, `topics`, `subtopics`

Document, question, resource and learning tables:

- `uploaded_documents`, `question_papers`, `document_pages`
- `questions`, `question_topic_map`, `question_occurrences`, `solutions`, `content_reviews`
- `learning_resources`, `student_progress`, `bookmarks`, `quiz_attempts`, `student_topic_activity`
- `ai_interactions`, including an optional 1536-dimension pgvector embedding column

Primary keys use UUIDs except the branch-subject offering composite key. Foreign keys preserve existing ownership behavior. Academic imports use deterministic IDs and natural-key constraints; they do not delete existing records.
