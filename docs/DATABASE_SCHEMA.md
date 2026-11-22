# Database Schema

Core hierarchy:

`colleges -> branches -> academic_schemes -> semesters -> subjects -> units -> topics -> subtopics`

Student and academic tables:

- `users`, `student_profiles`, `student_subject_enrollments`
- `colleges`, `branches`, `academic_schemes`, `semesters`, `subjects`
- `elective_baskets`, `elective_options`
- `syllabus_versions`, `syllabus_documents`

Document tables:

- `uploaded_documents`, `question_papers`, `document_pages`
- `questions`, `question_topic_map`, `question_occurrences`
- `solutions`, `content_reviews`

Future tracking and AI tables:

- `student_progress`, `bookmarks`, `quiz_attempts`, `student_topic_activity`
- `ai_interactions`, including an optional 1536-dimension pgvector embedding column

Primary keys use UUIDs. Foreign keys use CASCADE or SET NULL according to the safe ownership relationship. Unique constraints prevent duplicate catalog and enrollment records.
