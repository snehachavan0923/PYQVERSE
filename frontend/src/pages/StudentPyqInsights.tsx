import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useStudentSubjects } from '../hooks/useStudentSubjects'
import { errorDetail } from '../services/authApi'
import {
  getStudentAnalysis,
  type StudentSubjectAnalysisResult,
  type TopicInsightItem,
} from '../services/analysisApi'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import { LoadingState, ErrorState } from '../components/PageState'

export default function StudentPyqInsights() {
  const { session } = useAuth()
  const subjects = useStudentSubjects()
  const [selectedSubjectId, setSelectedSubjectId] = useState<string>('')
  const [analysis, setAnalysis] = useState<StudentSubjectAnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expandedTopic, setExpandedTopic] = useState<string | null>(null)

  // Default to first enrolled subject if none selected
  useEffect(() => {
    if (!selectedSubjectId && subjects && subjects.length > 0) {
      setSelectedSubjectId(subjects[0].id)
    }
  }, [subjects, selectedSubjectId])

  const loadAnalysis = useCallback(() => {
    if (!selectedSubjectId) return
    setLoading(true)
    setError('')
    getStudentAnalysis(session, selectedSubjectId)
      .then((data) => setAnalysis(data))
      .catch((err) => setError(errorDetail(err, 'Unable to load AI PYQ insights for this subject')))
      .finally(() => setLoading(false))
  }, [session, selectedSubjectId])

  useEffect(() => {
    loadAnalysis()
  }, [loadAnalysis])

  const getPriorityBadge = (category: TopicInsightItem['priority_category']) => {
    switch (category) {
      case 'VERY_HIGH':
        return <span style={{ backgroundColor: '#dc2626', color: '#fff', fontSize: '0.75rem', fontWeight: 700, padding: '0.2rem 0.5rem', borderRadius: '4px' }}>MUST STUDY</span>
      case 'HIGH':
        return <span style={{ backgroundColor: '#f97316', color: '#fff', fontSize: '0.75rem', fontWeight: 600, padding: '0.2rem 0.5rem', borderRadius: '4px' }}>HIGH PRIORITY</span>
      case 'MEDIUM':
        return <span style={{ backgroundColor: '#6366f1', color: '#fff', fontSize: '0.75rem', fontWeight: 500, padding: '0.2rem 0.5rem', borderRadius: '4px' }}>MEDIUM</span>
      case 'INSUFFICIENT_DATA':
        return <span style={{ backgroundColor: '#64748b', color: '#fff', fontSize: '0.75rem', padding: '0.2rem 0.5rem', borderRadius: '4px' }}>PRELIMINARY</span>
      case 'LOW':
      default:
        return <span style={{ backgroundColor: '#334155', color: '#94a3b8', fontSize: '0.75rem', padding: '0.2rem 0.5rem', borderRadius: '4px' }}>LOW FREQ</span>
    }
  }

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="AI Intelligence Engine"
        title="PYQ Historical Insights"
        description="Exam frequency trends, syllabus unit distribution, and high-return topic recommendations based on past papers."
      />

      {/* Subject Filter Bar */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '1rem',
          backgroundColor: 'rgba(30, 41, 59, 0.5)',
          padding: '1rem',
          borderRadius: '8px',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          marginBottom: '1.5rem',
        }}
      >
        <label htmlFor="subject-select" style={{ fontWeight: 600, color: '#f1f5f9', fontSize: '0.95rem' }}>
          Select Subject:
        </label>
        <select
          id="subject-select"
          value={selectedSubjectId}
          onChange={(e) => setSelectedSubjectId(e.target.value)}
          style={{
            backgroundColor: '#0f172a',
            color: '#f8fafc',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            borderRadius: '6px',
            padding: '0.5rem 1rem',
            fontSize: '0.95rem',
            minWidth: '260px',
          }}
        >
          {subjects.map((s) => (
            <option key={s.id} value={s.id}>
              {s.code} — {s.name}
            </option>
          ))}
        </select>

        <button
          type="button"
          onClick={loadAnalysis}
          className="content-btn is-secondary"
          style={{ padding: '0.45rem 0.9rem', fontSize: '0.85rem' }}
        >
          Refresh Insights
        </button>
      </div>

      {loading && <LoadingState label="Analyzing historical exam trends and topic frequencies..." />}

      {error && !loading && <ErrorState message={error} onRetry={loadAnalysis} />}

      {!loading && !error && analysis && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Insufficient Data Warning Banner */}
          {analysis.recommendations?.insufficient_data && (
            <div
              style={{
                backgroundColor: 'rgba(245, 158, 11, 0.1)',
                border: '1px solid rgba(245, 158, 11, 0.3)',
                borderRadius: '8px',
                padding: '0.9rem 1.25rem',
                color: '#fde68a',
                fontSize: '0.9rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
              }}
            >
              <span>ℹ️</span>
              <span>
                <strong>Limited Past Papers Available:</strong> {analysis.total_papers} paper(s) indexed for this subject. Insights reflect current historical data and will sharpen as more papers are uploaded.
              </span>
            </div>
          )}

          {/* Overview Stat Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
            <div className="admin-content-card" style={{ padding: '1.25rem' }}>
              <div style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.35rem' }}>Analyzed Question Papers</div>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#f8fafc' }}>{analysis.total_papers}</div>
              <div style={{ color: '#64748b', fontSize: '0.8rem', marginTop: '0.2rem' }}>CIE & SEE Exams</div>
            </div>

            <div className="admin-content-card" style={{ padding: '1.25rem' }}>
              <div style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.35rem' }}>Extracted Questions</div>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#f8fafc' }}>{analysis.total_questions}</div>
              <div style={{ color: '#64748b', fontSize: '0.8rem', marginTop: '0.2rem' }}>Indexed & Classified</div>
            </div>

            <div className="admin-content-card" style={{ padding: '1.25rem' }}>
              <div style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.35rem' }}>Syllabus Exam Coverage</div>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#10b981' }}>{analysis.coverage_score}%</div>
              <div style={{ backgroundColor: 'rgba(255,255,255,0.1)', height: '5px', borderRadius: '3px', marginTop: '0.5rem', overflow: 'hidden' }}>
                <div style={{ width: `${analysis.coverage_score}%`, height: '100%', backgroundColor: '#10b981' }} />
              </div>
            </div>
          </div>

          {/* Unit-Wise Weightage & Question Distribution */}
          <div className="admin-content-card">
            <h2 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#f8fafc', marginBottom: '1rem' }}>
              Unit-wise Marks & Question Distribution
            </h2>
            {analysis.unit_stats.length === 0 ? (
              <EmptyState title="No Unit Data" description="Upload question papers to compute syllabus weightage distribution." />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                {analysis.unit_stats.map((u) => (
                  <div key={u.unit_number} style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                      <span style={{ fontWeight: 600, color: '#f1f5f9' }}>
                        Unit {u.unit_number}: {u.title}
                      </span>
                      <span style={{ color: '#94a3b8' }}>
                        {u.question_count} questions • {u.total_marks} marks ({u.marks_percentage}%)
                      </span>
                    </div>
                    <div style={{ backgroundColor: 'rgba(255,255,255,0.08)', height: '10px', borderRadius: '5px', overflow: 'hidden' }}>
                      <div
                        style={{
                          width: `${Math.min(u.marks_percentage, 100)}%`,
                          height: '100%',
                          backgroundColor: '#6366f1',
                          borderRadius: '5px',
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* High Return Topics & Importance Scoring */}
          <div className="admin-content-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div>
                <h2 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#f8fafc' }}>
                  Topic Importance & Exam Frequency
                </h2>
                <p style={{ color: '#94a3b8', fontSize: '0.85rem' }}>
                  Ranked by our priority scoring algorithm (Frequency 40%, Marks 30%, Recency 20%, Repeats 10%).
                </p>
              </div>
            </div>

            {analysis.topic_insights.length === 0 ? (
              <EmptyState title="No Topics Mapped Yet" description="Questions are being classified by the background engine." />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {analysis.topic_insights.map((t) => (
                  <div
                    key={t.topic_title}
                    style={{
                      backgroundColor: 'rgba(30, 41, 59, 0.6)',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      borderRadius: '8px',
                      padding: '1rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <span style={{ fontWeight: 600, color: '#f8fafc', fontSize: '1rem' }}>{t.topic_title}</span>
                          {getPriorityBadge(t.priority_category)}
                        </div>
                        <div style={{ color: '#94a3b8', fontSize: '0.8rem', marginTop: '0.2rem' }}>
                          Unit {t.unit_number} • Asked {t.frequency} times ({t.total_marks} total marks) • Last appeared {t.last_appeared_year || 'N/A'}
                        </div>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#a855f7' }}>
                            {t.priority_score}<span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>/100</span>
                          </div>
                          <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Priority Index</div>
                        </div>

                        <button
                          type="button"
                          onClick={() => setExpandedTopic(expandedTopic === t.topic_title ? null : t.topic_title)}
                          className="content-btn is-secondary"
                          style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem' }}
                        >
                          {expandedTopic === t.topic_title ? 'Hide Questions' : 'View Questions'}
                        </button>
                      </div>
                    </div>

                    {/* Expandable Sample Questions */}
                    {expandedTopic === t.topic_title && t.sample_questions && t.sample_questions.length > 0 && (
                      <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                        <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#cbd5e1', marginBottom: '0.4rem' }}>
                          Historical Exam Questions:
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                          {t.sample_questions.map((sq, idx) => (
                            <div
                              key={idx}
                              style={{
                                backgroundColor: 'rgba(15, 23, 42, 0.6)',
                                padding: '0.5rem 0.75rem',
                                borderRadius: '4px',
                                fontSize: '0.85rem',
                                color: '#e2e8f0',
                              }}
                            >
                              <span style={{ color: '#60a5fa', fontWeight: 600, marginRight: '0.4rem' }}>
                                Q{sq.question_number} {sq.year ? `(${sq.year})` : ''}:
                              </span>
                              {sq.text}
                              {sq.marks && <span style={{ color: '#94a3b8', marginLeft: '0.5rem' }}>[{sq.marks}M]</span>}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Repeated Question Clusters */}
          {analysis.repeated_clusters && analysis.repeated_clusters.length > 0 && (
            <div className="admin-content-card">
              <h2 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.5rem' }}>
                Frequently Repeated Questions
              </h2>
              <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '1rem' }}>
                Exact or reworded questions that have appeared across multiple exam cycles.
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {analysis.repeated_clusters.map((c, idx) => (
                  <div
                    key={idx}
                    style={{
                      backgroundColor: 'rgba(30, 41, 59, 0.5)',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      borderRadius: '8px',
                      padding: '0.9rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                      <span style={{ color: '#34d399', fontSize: '0.8rem', fontWeight: 600 }}>
                        {c.repeat_category.replace('_', ' ')} • {Math.round(c.similarity_score * 100)}% Match
                      </span>
                      {c.source_marks && <span style={{ color: '#94a3b8', fontSize: '0.8rem' }}>{c.source_marks} Marks</span>}
                    </div>
                    <div style={{ color: '#f1f5f9', fontSize: '0.9rem', marginBottom: '0.4rem' }}>
                      "{c.source_text}"
                    </div>
                    {c.explanation && (
                      <div style={{ color: '#64748b', fontSize: '0.75rem' }}>{c.explanation}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Student Preparation Recommendations & Coverage Gaps */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem' }}>
            <div className="admin-content-card">
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.75rem' }}>
                🎯 High-Return Topics (Study First)
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {analysis.recommendations?.study_first?.map((item, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      backgroundColor: 'rgba(255,255,255,0.03)',
                      padding: '0.6rem 0.8rem',
                      borderRadius: '6px',
                    }}
                  >
                    <span style={{ color: '#e2e8f0', fontSize: '0.9rem' }}>
                      {idx + 1}. {item.topic_title} (Unit {item.unit_number})
                    </span>
                    <span style={{ color: '#a855f7', fontWeight: 600, fontSize: '0.85rem' }}>
                      {item.priority_score} pts
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="admin-content-card">
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.75rem' }}>
                🔍 Syllabus Coverage Gaps
              </h3>
              <p style={{ color: '#94a3b8', fontSize: '0.8rem', marginBottom: '0.5rem' }}>
                Topics in the syllabus that have rarely or never appeared in past papers:
              </p>
              {analysis.recommendations?.coverage_gaps?.length === 0 ? (
                <div style={{ color: '#10b981', fontSize: '0.85rem' }}>All syllabus topics have appeared in past exams.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {analysis.recommendations?.coverage_gaps?.slice(0, 5).map((gap, idx) => (
                    <div
                      key={idx}
                      style={{
                        backgroundColor: 'rgba(255,255,255,0.03)',
                        padding: '0.6rem 0.8rem',
                        borderRadius: '6px',
                        fontSize: '0.85rem',
                        color: '#cbd5e1',
                      }}
                    >
                      Unit {gap.unit_number}: <strong>{gap.topic_title}</strong>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
