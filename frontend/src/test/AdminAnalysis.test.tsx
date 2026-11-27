import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const mocks = vi.hoisted(() => ({
  listAnalysisJobs: vi.fn(),
  getAnalysisOverview: vi.fn(),
  syncAnalysisJobs: vi.fn(),
  listFlaggedQuestions: vi.fn(),
  retryAnalysisJob: vi.fn(),
  correctQuestion: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ session: { access_token: 'fake-token' } }),
}))

vi.mock('../services/analysisApi', () => ({
  listAnalysisJobs: mocks.listAnalysisJobs,
  getAnalysisOverview: mocks.getAnalysisOverview,
  syncAnalysisJobs: mocks.syncAnalysisJobs,
  listFlaggedQuestions: mocks.listFlaggedQuestions,
  retryAnalysisJob: mocks.retryAnalysisJob,
  correctQuestion: mocks.correctQuestion,
}))

vi.mock('../services/notification', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

import AdminAnalysis from '../pages/AdminAnalysis'

describe('AdminAnalysis Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getAnalysisOverview.mockResolvedValue({
      total_documents: 1,
      pending_jobs: 0,
      processing_jobs: 0,
      completed_jobs: 1,
      failed_jobs: 0,
      flagged_jobs: 0,
      documents_without_jobs: 0,
      extracted_questions: 12,
      classified_questions: 12,
      flagged_questions: 0,
      papers: [],
      ai_provider: { provider: 'rule_keyword', configured: false, model: null, deterministic: true, notes: [] },
    })
  })

  it('renders analysis jobs and switches tabs to flagged questions', async () => {
    mocks.listAnalysisJobs.mockResolvedValueOnce({
      items: [
        {
          id: 'job-1',
          question_paper_id: 'qp-1',
          uploaded_document_id: 'doc-1',
          title: '2025 SEE Exam Paper',
          original_filename: '2025_SEE.pdf',
          subject_id: 'sub-1',
          subject_code: '22CS52',
          subject_name: 'Computer Architecture',
          exam_type: 'SEE',
          examination_year: 2025,
          status: 'COMPLETED',
          stage: 'Analysis complete. All questions verified.',
          progress_percent: 100,
          total_questions: 12,
          mapped_questions: 12,
          flagged_questions: 0,
          average_confidence: 0.92,
          error_message: null,
          model_name: 'Rule/NLP Engine',
          model_provider: 'rule_keyword',
          started_at: '2026-11-27T10:00:00Z',
          completed_at: '2026-11-27T10:01:00Z',
          created_at: '2026-11-27T10:00:00Z',
        },
      ],
      total: 1,
    })

    mocks.listFlaggedQuestions.mockResolvedValueOnce({
      items: [
        {
          id: 'q-1',
          question_number: '3.b',
          extracted_text: 'Describe DMA controller data transfer modes.',
          marks: 8,
          original_page_number: 2,
          verification_status: 'PENDING',
          paper_id: 'qp-1',
          paper_title: '2025 SEE Exam Paper',
          subject_id: 'sub-1',
          subject_code: '22CS52',
          subject_name: 'Computer Architecture',
          storage_path: 'pyq/paper.pdf',
          classification: {
            main_topic: 'Direct Memory Access',
            subtopic: 'DMA Transfer',
            related_concepts: ['Bus Master'],
            question_type: 'THEORY',
            difficulty: 'MEDIUM',
            bloom_taxonomy: 'UNDERSTAND',
            unit_number: 3,
            suggested_unit_title: 'I/O Organization',
            suggested_topic_title: 'DMA',
            confidence: 0.62,
            explanation: 'Moderate confidence mapping.',
            provisional: true,
          },
        },
      ],
      total: 1,
    })

    render(<AdminAnalysis />)

    // Verify title rendered
    expect(screen.getByText('Automated PYQ Analysis')).toBeInTheDocument()

    // Verify job item is rendered
    await waitFor(() => {
      expect(screen.getByText('2025 SEE Exam Paper')).toBeInTheDocument()
      expect(screen.getByText('Completed')).toBeInTheDocument()
      expect(screen.getByText('100%')).toBeInTheDocument()
    })

    // Switch to Flagged tab
    const flaggedTab = screen.getByRole('button', { name: /Flagged for Review/i })
    await userEvent.click(flaggedTab)

    // Verify flagged question is rendered
    await waitFor(() => {
      expect(screen.getByText(/Q3.b/i)).toBeInTheDocument()
      expect(screen.getByText(/Describe DMA controller data transfer modes/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Calibrate & Approve/i })).toBeInTheDocument()
    })
  })
})
