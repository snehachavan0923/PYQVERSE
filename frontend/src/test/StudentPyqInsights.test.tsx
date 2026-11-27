import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getStudentAnalysis: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ session: { access_token: 'fake-token' } }),
}))

vi.mock('../hooks/useStudentSubjects', () => ({
  useStudentSubjects: () => [
    { id: 'sub-1', code: '22CS52', name: 'Computer Architecture' },
  ],
}))

vi.mock('../services/analysisApi', () => ({
  getStudentAnalysis: mocks.getStudentAnalysis,
}))

import StudentPyqInsights from '../pages/StudentPyqInsights'

describe('StudentPyqInsights Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders overview stats, unit breakdown, and high-return topic rankings', async () => {
    mocks.getStudentAnalysis.mockResolvedValue({
      subject_id: 'sub-1',
      subject_code: '22CS52',
      subject_name: 'Computer Architecture',
      total_papers: 4,
      total_questions: 36,
      coverage_score: 82.5,
      unit_stats: [
        {
          unit_id: 'u-1',
          unit_number: 1,
          title: 'Basic Structure of Computers',
          question_count: 8,
          total_marks: 55,
          marks_percentage: 27.5,
        },
      ],
      topic_insights: [
        {
          topic_title: 'Pipelining & Hazards',
          unit_number: 1,
          frequency: 5,
          total_marks: 40,
          last_appeared_year: 2025,
          years_appeared: [2025, 2024, 2023],
          cie_frequency: 2,
          see_frequency: 3,
          priority_score: 92.0,
          priority_category: 'VERY_HIGH',
          score_breakdown: {
            frequency_score: 40,
            marks_score: 30,
            recency_score: 20,
            repeat_bonus: 2,
          },
          sample_questions: [
            {
              question_number: '2.a',
              text: 'Explain pipeline data hazards and forwarding technique.',
              marks: 8,
              year: 2025,
            },
          ],
        },
      ],
      repeated_clusters: [
        {
          source_id: 'q-1',
          source_text: 'Explain pipelining with hazards.',
          source_marks: 8,
          target_id: 'q-2',
          target_text: 'What is pipelining? Explain data hazards.',
          target_marks: 8,
          similarity_score: 0.88,
          repeat_category: 'EXACT_REPEAT',
          explanation: 'Identical conceptual question.',
        },
      ],
      recommendations: {
        study_first: [
          { topic_title: 'Pipelining & Hazards', unit_number: 1, priority_score: 92.0 },
        ],
        frequent_repeats: [],
        revision_order: [
          { topic_title: 'Pipelining & Hazards', unit_number: 1, rank: 1 },
        ],
        coverage_gaps: [],
        insufficient_data: false,
      },
      calculated_at: '2026-11-27T10:00:00Z',
    })

    render(<StudentPyqInsights />)

    expect(screen.getByText('PYQ Historical Insights')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('82.5%')).toBeInTheDocument()
      expect(screen.getByText('Pipelining & Hazards')).toBeInTheDocument()
      expect(screen.getByText('MUST STUDY')).toBeInTheDocument()
      expect(screen.getByText(/Basic Structure of Computers/i)).toBeInTheDocument()
    })
  })
})
