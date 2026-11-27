import { getWithAuth, postWithAuth, patchWithAuth } from './authApi'
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

export interface TopicInsightItem {
  topic_title: string
  unit_number: number
  frequency: number
  total_marks: number
  last_appeared_year: number | null
  years_appeared: number[]
  cie_frequency: number
  see_frequency: number
  priority_score: number
  priority_category: 'VERY_HIGH' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INSUFFICIENT_DATA'
  score_breakdown: {
    frequency_score: number
    marks_score: number
    recency_score: number
    repeat_bonus: number
  }
  sample_questions: Array<{
    question_number: string
    text: string
    marks: number | null
    year: number | null
  }>
}

export interface StudentSubjectAnalysisResult {
  subject_id: string
  subject_code: string
  subject_name: string
  total_papers: number
  total_questions: number
  coverage_score: number
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
    target_id: string
    target_text: string
    target_marks: number | null
    similarity_score: number
    repeat_category: string
    explanation: string
  }>
  recommendations: {
    study_first: Array<{
      topic_title: string
      unit_number: number
      priority_score: number
    }>
    frequent_repeats: Array<{
      text: string
      marks: number | null
      similarity: number
    }>
    revision_order: Array<{
      topic_title: string
      unit_number: number
      rank: number
    }>
    coverage_gaps: Array<{
      unit_number: number
      unit_title: string
      topic_title: string
    }>
    insufficient_data?: boolean
  }
  calculated_at: string | null
}

function query(params: Record<string, string | number | undefined>) {
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
    classification: any
  }>(`/admin/analysis/questions/${questionId}`, session, payload)
}

export function getStudentAnalysis(session: AuthSession | null, subjectId: string) {
  return getWithAuth<StudentSubjectAnalysisResult>(`/student/analysis/${subjectId}`, session)
}
