import { getWithAuth, postWithAuth, patchWithAuth, deleteWithAuth } from './authApi'
import type { AuthSession } from '../types/auth'

export interface AnalysisJobItem {
  id: string
  question_paper_id: string
  uploaded_document_id: string
  title: string
  original_filename: string
  subject_id: string
  subject_code: string | null
  subject_name: string | null
  exam_type: string
  examination_year: number
  status: 'PENDING' | 'EXTRACTING' | 'CLASSIFYING' | 'MAPPING' | 'ANALYZING' | 'COMPLETED' | 'FAILED' | 'FLAGGED_REVIEW'
  stage: string | null
  progress_percent: number
  total_questions: number
  mapped_questions: number
  flagged_questions: number
  average_confidence: number | null
  error_message: string | null
  model_name: string | null
  model_provider: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string | null
}

export interface QuestionClassificationData {
  main_topic: string | null
  subtopic: string | null
  related_concepts: string[]
  question_type: string | null
  difficulty: string | null
  bloom_taxonomy: string | null
  unit_number: number | null
  suggested_unit_title: string | null
  suggested_topic_title: string | null
  confidence: number | null
  explanation: string | null
  provisional: boolean
}

export interface FlaggedQuestionItem {
  id: string
  question_number: string
  extracted_text: string
  marks: number | null
  original_page_number: number | null
  verification_status: string
  paper_id: string
  paper_title: string
  subject_id: string | null
  subject_code: string | null
  subject_name: string | null
  storage_path: string
  classification: QuestionClassificationData
}

export interface PaperAnalysisStatus {
  paper_id: string
  document_id: string
  title: string
  original_filename?: string
  exam_type: string
  examination_year: number | null
  cie_number: number | null
  job_status: string
  stage: string | null
  progress_percent: number
  question_count: number
  classified_count: number
  flagged_count: number
  error_message: string | null
  uploaded_at?: string | null
}

export interface TopicInsightItem {
  topic_key?: string
  topic_title: string
  unit_number: number | null
  frequency: number
  papers_appeared?: number
  questions_with_marks?: number
  total_marks: number
  last_appeared_year: number | null
  years_appeared: number[]
  cie_frequency: number
  see_frequency: number
  repeat_count?: number
  priority_score: number
  priority_category: 'VERY_HIGH' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INSUFFICIENT_DATA'
  priority_label?: string
  why_important?: string
  provisional?: boolean
  score_breakdown: {
    frequency_score: number
    marks_score: number
    recency_score: number
    repeat_bonus: number
  }
  question_type_distribution?: Record<string, number>
  difficulty_distribution?: Record<string, number>
  related_concepts?: string[]
  sample_questions: Array<{
    question_id?: string
    question_number: string
    text: string
    marks: number | null
    year: number | null
    exam_type?: string | null
    paper_id?: string
    paper_title?: string
    page_number?: number | null
  }>
  learning_status?: string
  learning_explanation?: string | null
}

export interface StudentSubjectAnalysisResult {
  subject_id: string
  subject_code: string
  subject_name: string
  total_papers: number
  total_questions: number
  coverage_score: number | null
  syllabus_status?: 'AVAILABLE' | 'PENDING'
  data_availability?: 'AVAILABLE' | 'PARTIAL' | 'NO_QUESTIONS'
  topics_discovered?: number
  repeated_question_count?: number
  unit_stats: Array<{
    unit_id: string | null
    unit_number: number
    title: string
    question_count: number
    total_marks: number
    marks_percentage: number
  }>
  topic_insights: TopicInsightItem[]
  repeated_clusters: Array<{
    source_id: string
    source_text: string
    source_marks: number | null
    source_question_number?: string
    source_topic?: string | null
    source_paper?: PaperAnalysisStatus
    target_id: string
    target_text: string
    target_marks: number | null
    target_question_number?: string
    target_topic?: string | null
    target_paper?: PaperAnalysisStatus
    similarity_score: number
    repeat_category: string
    explanation: string
  }>
  recommendations: {
    study_first: Array<{
      topic_title: string
      unit_number: number | null
      priority_score: number
      priority_label?: string
    }>
    frequent_repeats: Array<{
      text: string
      marks: number | null
      similarity: number
      repeat_category?: string
    }>
    revision_order: Array<{
      topic_title: string
      unit_number: number | null
      rank: number
    }>
    coverage_gaps: Array<{
      unit_number: number
      unit_title: string
      topic_title: string
    }>
    insufficient_data?: boolean
    syllabus_status?: 'AVAILABLE' | 'PENDING'
    ai_provider?: {
      provider: string
      configured: boolean
      model: string | null
      deterministic: boolean
      notes: string[]
    }
    data_notes?: string[]
  }
  papers?: PaperAnalysisStatus[]
  ai_provider?: {
    provider: string
    configured: boolean
    model: string | null
    deterministic: boolean
    notes: string[]
  }
  bookmarked_question_ids?: string[]
  topic_progress?: Array<{
    topic_key: string
    topic_title: string
    status: string
    explanation: string | null
    updated_at: string | null
  }>
  calculated_at: string | null
}

export interface AnalysisOverview {
  total_documents: number
  pending_jobs: number
  processing_jobs: number
  completed_jobs: number
  failed_jobs: number
  flagged_jobs: number
  documents_without_jobs: number
  extracted_questions: number
  classified_questions: number
  flagged_questions: number
  papers: Array<PaperAnalysisStatus & { subject_id: string; subject_code: string | null; subject_name: string | null }>
  ai_provider: {
    provider: string
    configured: boolean
    model: string | null
    deterministic: boolean
    notes: string[]
  }
}

export interface StudentQuestionItem {
  id: string
  question_number: string
  sequence: number
  extracted_text: string
  marks: number | null
  original_page_number: number | null
  verification_status: string
  bookmarked: boolean
  bookmarked_at?: string | null
  paper: {
    paper_id: string
    document_id: string
    title: string
    original_filename: string
    exam_type: string | null
    examination_year: number | null
    cie_number: number | null
  }
  subject: {
    id: string
    code: string
    name: string
  }
  classification: QuestionClassificationData | null
  repeat_count: number
  max_similarity: number | null
}

export interface StudentLearningOverview {
  subjects: Array<{
    subject_id: string
    subject_code: string
    subject_name: string
    papers_count: number
    questions_analysed: number
    topics_discovered: number
    bookmarked_questions: number
    topics_learned: number
    topics_needing_revision: number
    syllabus_status: string
    top_priority_topic: TopicInsightItem | null
    has_pyqs: boolean
  }>
  totals: {
    subjects_with_pyqs: number
    questions_analysed: number
    topics_discovered: number
    bookmarked_questions: number
    topics_learned: number
    topics_needing_revision: number
  }
}

export interface TopicDetailResult {
  subject_id: string
  subject_code: string
  subject_name: string
  topic: TopicInsightItem & {
    topic_key: string
    learning_status: string
    learning_explanation: string | null
    learning_updated_at: string | null
  }
  resources: Array<{
    id: string
    title: string
    description: string | null
    resource_type: string
    resource_source: string
    external_url: string | null
    link_title: string | null
    original_filename: string | null
    file_type: string | null
    file_size: number | null
    unit_id: string | null
    unit_title: string | null
    uploaded_at: string | null
  }>
  related_questions: StudentQuestionItem[]
}

function query(params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value))
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

export function listAnalysisJobs(
  session: AuthSession | null,
  params: { status?: string; subject_id?: string; limit?: number; offset?: number } = {},
) {
  return getWithAuth<{ items: AnalysisJobItem[]; total: number }>(
    `/admin/analysis/jobs${query(params)}`,
    session,
  )
}

export function getAnalysisOverview(session: AuthSession | null) {
  return getWithAuth<AnalysisOverview>('/admin/analysis/overview', session)
}

export function syncAnalysisJobs(
  session: AuthSession | null,
  payload: { run?: boolean; force?: boolean } = { run: true, force: false },
) {
  return postWithAuth<{
    message: string
    created: number
    reset: number
    skipped: number
    scheduled_job_ids: string[]
    run: boolean
  }>('/admin/analysis/sync', session, payload)
}

export function analyzePaper(session: AuthSession | null, paperId: string) {
  return postWithAuth<{ message: string; job_id: string; status: string }>(
    `/admin/analysis/papers/${paperId}/analyze?force=true`,
    session,
  )
}

export function retryAnalysisJob(session: AuthSession | null, jobId: string) {
  return postWithAuth<{ message: string; job_id: string; status: string }>(
    `/admin/analysis/jobs/${jobId}/retry`,
    session,
  )
}

export function listFlaggedQuestions(
  session: AuthSession | null,
  params: { subject_id?: string; limit?: number; offset?: number } = {},
) {
  return getWithAuth<{ items: FlaggedQuestionItem[]; total: number }>(
    `/admin/analysis/flagged${query(params)}`,
    session,
  )
}

export function correctQuestion(
  session: AuthSession | null,
  questionId: string,
  payload: {
    extracted_text?: string
    marks?: number
    main_topic?: string
    subtopic?: string
    unit_number?: number
    topic_id?: string
    action?: 'APPROVE' | 'REJECT' | 'UPDATE'
  },
) {
  return patchWithAuth<{
    message: string
    question_id: string
    verification_status: string
    extracted_text: string
    marks: number | null
    classification: unknown
  }>(`/admin/analysis/questions/${questionId}`, session, payload)
}

export function getStudentAnalysis(session: AuthSession | null, subjectId: string) {
  return getWithAuth<StudentSubjectAnalysisResult>(`/student/analysis/${subjectId}`, session)
}

export function getLearningOverview(session: AuthSession | null) {
  return getWithAuth<StudentLearningOverview>('/student/learning/overview', session)
}

export function listStudentTopics(session: AuthSession | null, subjectId: string) {
  return getWithAuth<{
    subject_id: string
    subject_code: string
    subject_name: string
    syllabus_status: string
    items: TopicInsightItem[]
  }>(`/student/subjects/${subjectId}/topics`, session)
}

export function getStudentTopic(
  session: AuthSession | null,
  subjectId: string,
  topicKey: string,
) {
  return getWithAuth<TopicDetailResult>(
    `/student/subjects/${subjectId}/topics/${encodeURIComponent(topicKey)}`,
    session,
  )
}

export function updateTopicProgress(
  session: AuthSession | null,
  subjectId: string,
  topicKey: string,
  payload: { status: string; topic_title?: string; explanation?: string },
) {
  return patchWithAuth<{
    message: string
    topic_key: string
    topic_title: string
    status: string
    explanation: string | null
    updated_at: string | null
  }>(`/student/subjects/${subjectId}/topics/${encodeURIComponent(topicKey)}`, session, payload)
}

export function listStudentQuestions(
  session: AuthSession | null,
  params: {
    subject_id?: string
    topic_key?: string
    bookmarked?: boolean
    repeated_only?: boolean
    search?: string
    limit?: number
    offset?: number
  } = {},
) {
  return getWithAuth<{ items: StudentQuestionItem[]; total: number }>(
    `/student/questions${query(params)}`,
    session,
  )
}

export function getStudentQuestion(session: AuthSession | null, questionId: string) {
  return getWithAuth<StudentQuestionItem>(`/student/questions/${questionId}`, session)
}

export function bookmarkQuestion(session: AuthSession | null, questionId: string) {
  return postWithAuth<{ message: string; question_id: string; bookmarked: boolean }>(
    `/student/bookmarks/questions/${questionId}`,
    session,
  )
}

export function removeQuestionBookmark(session: AuthSession | null, questionId: string) {
  return deleteWithAuth<{ message: string; question_id: string; bookmarked: boolean }>(
    `/student/bookmarks/questions/${questionId}`,
    session,
  )
}

export function listBookmarkedQuestions(
  session: AuthSession | null,
  params: { subject_id?: string; limit?: number; offset?: number } = {},
) {
  return getWithAuth<{ items: StudentQuestionItem[]; total: number }>(
    `/student/bookmarks/questions${query(params)}`,
    session,
  )
}
