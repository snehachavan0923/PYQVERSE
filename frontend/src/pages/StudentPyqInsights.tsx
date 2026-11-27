import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useStudentSubjects } from '../hooks/useStudentSubjects'
import { errorDetail } from '../services/authApi'
import {
  getStudentAnalysis,
  listBookmarkedQuestions,
  bookmarkQuestion,
  removeQuestionBookmark,
  updateTopicProgress,
  type StudentQuestionItem,
  type StudentSubjectAnalysisResult,
  type TopicInsightItem,
} from '../services/analysisApi'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import { LoadingState, ErrorState } from '../components/PageState'
import notifications from '../services/notification'

const LEARNING_OPTIONS = [
  { value: 'NOT_STARTED', label: 'Not started' },
  { value: 'LEARNING', label: 'Learning' },
  { value: 'LEARNED', label: 'Learned' },
  { value: 'NEEDS_REVISION', label: 'Needs revision' },
]

function topicKey(topic: TopicInsightItem) {
  if (topic.topic_key) return topic.topic_key
  return (
    topic.topic_title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 120) || 'general-topic'
  )
}

export default function StudentPyqInsights() {
  const { session } = useAuth()
  const subjects = useStudentSubjects()
  const [selectedSubjectId, setSelectedSubjectId] = useState<string>('')
  const [analysis, setAnalysis] = useState<StudentSubjectAnalysisResult | null>(null)
  const [bookmarks, setBookmarks] = useState<StudentQuestionItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expandedTopic, setExpandedTopic] = useState<string | null>(null)
  const [savingTopic, setSavingTopic] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedSubjectId && subjects && subjects.length > 0) {
      setSelectedSubjectId(subjects[0].id)
    }
  }, [subjects, selectedSubjectId])

  const loadBookmarks = useCallback(
    (subjectId: string) => {
      if (typeof listBookmarkedQuestions !== 'function') return
      listBookmarkedQuestions(session, { subject_id: subjectId })
        .then((data) => setBookmarks(data.items))
        .catch(() => setBookmarks([]))
    },
    [session],
  )

  const loadAnalysis = useCallback(() => {
    if (!selectedSubjectId) return
    setLoading(true)
    setError('')
    getStudentAnalysis(session, selectedSubjectId)
      .then((data) => {
        setAnalysis(data)
        loadBookmarks(selectedSubjectId)
      })
      .catch((err) => setError(errorDetail(err, 'Unable to load AI PYQ insights for this subject')))
      .finally(() => setLoading(false))
  }, [session, selectedSubjectId, loadBookmarks])

  useEffect(() => {
    loadAnalysis()
  }, [loadAnalysis])

  const setTopicStatus = async (topic: TopicInsightItem, status: string) => {
    const key = topicKey(topic)
    setSavingTopic(key)
    try {
      if (typeof updateTopicProgress === 'function') {
        await updateTopicProgress(session, selectedSubjectId, key, {
          status,
          topic_title: topic.topic_title,
        })
      }
      setAnalysis((current) =>
        current
          ? {
              ...current,
              topic_insights: current.topic_insights.map((item) =>
                topicKey(item) === key ? { ...item, learning_status: status } : item,
              ),
            }
          : current,
      )
      notifications.success('Topic progress updated')
    } catch (err) {
      notifications.error(errorDetail(err, 'Failed to update topic progress'))
    } finally {
      setSavingTopic(null)
    }
  }

  const toggleBookmark = async (questionId?: string) => {
    if (!questionId || typeof bookmarkQuestion !== 'function') return
    const existing = bookmarks.some((item) => item.id === questionId)
    try {
      if (existing && typeof removeQuestionBookmark === 'function') {
        await removeQuestionBookmark(session, questionId)
        setBookmarks((current) => current.filter((item) => item.id !== questionId))
        notifications.success('Bookmark removed')
      } else {
        await bookmarkQuestion(session, questionId)
        loadBookmarks(selectedSubjectId)
        notifications.success('Question bookmarked')
      }
    } catch (err) {
      notifications.error(errorDetail(err, 'Failed to update bookmark'))
    }
  }

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

  const getJobBadge = (status: string) => {
    const color =
      status === 'COMPLETED'
        ? '#10b981'
        : status === 'FLAGGED_REVIEW'
          ? '#f59e0b'
          : status === 'FAILED'
            ? '#ef4444'
            : status === 'NOT_QUEUED'
              ? '#64748b'
              : '#6366f1'
    return (
      <span style={{ backgroundColor: `${color}22`, color, fontSize: '0.75rem', fontWeight: 600, padding: '0.2rem 0.5rem', borderRadius: '4px' }}>
        {status.replace('_', ' ')}
      </span>
    )
  }

  const dataAvailability = analysis?.data_availability || (analysis && analysis.total_questions > 0 ? 'AVAILABLE' : 'NO_QUESTIONS')
  const syllabusStatus = analysis?.syllabus_status || analysis?.recommendations?.syllabus_status || 'PENDING'
  const coverageAvailable = syllabusStatus !== 'PENDING' && analysis?.coverage_score !== null && analysis?.coverage_score !== undefined
  const bookmarkedIds = new Set([
    ...(analysis?.bookmarked_question_ids || []),
    ...bookmarks.map((item) => item.id),
  ])

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="AI Intelligence Engine"
        title="PYQ Historical Insights"
        description="Exam frequency trends, provisional topic intelligence, bookmarks, and personal learning progress based only on analysed past papers."
      />

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
              {s.code} - {s.name}
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
          {dataAvailability === 'NO_QUESTIONS' && (
            <div style={{ backgroundColor: 'rgba(100, 116, 139, 0.12)', border: '1px solid rgba(148, 163, 184, 0.35)', borderRadius: '8px', padding: '1rem 1.25rem', color: '#cbd5e1' }}>
              <strong>No readable PYQ questions are available for this subject yet.</strong>{' '}
              The paper may be scanned, queued, or failed extraction. Check the paper status below. No statistics are fabricated.
            </div>
          )}

          {dataAvailability === 'PARTIAL' && (
            <div style={{ backgroundColor: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: '8px', padding: '0.9rem 1.25rem', color: '#fde68a', fontSize: '0.9rem' }}>
              <strong>Partial analysis:</strong> some papers are queued or failed extraction. Insights currently reflect only successfully analysed papers.
            </div>
          )}

          {syllabusStatus === 'PENDING' && (
            <div style={{ backgroundColor: 'rgba(99, 102, 241, 0.12)', border: '1px solid rgba(99, 102, 241, 0.3)', borderRadius: '8px', padding: '0.9rem 1.25rem', color: '#c7d2fe', fontSize: '0.9rem' }}>
              <strong>Syllabus not available:</strong> topics are provisional, discovered from PYQ text. Unit coverage is pending until an official syllabus is uploaded.
            </div>
          )}

          {analysis.recommendations?.insufficient_data && (
            <div style={{ backgroundColor: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: '8px', padding: '0.9rem 1.25rem', color: '#fde68a', fontSize: '0.9rem' }}>
              <strong>Limited past papers available:</strong> {analysis.total_papers} paper(s) indexed for this subject. Priority signals are preliminary.
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
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
              <div style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.35rem' }}>Topics Discovered</div>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#a855f7' }}>{analysis.topics_discovered ?? analysis.topic_insights.length}</div>
              <div style={{ color: '#64748b', fontSize: '0.8rem', marginTop: '0.2rem' }}>{syllabusStatus === 'PENDING' ? 'Provisional' : 'Syllabus mapped'}</div>
            </div>

            <div className="admin-content-card" style={{ padding: '1.25rem' }}>
              <div style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.35rem' }}>Repeated Questions</div>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#34d399' }}>{analysis.repeated_question_count ?? analysis.repeated_clusters.length}</div>
              <div style={{ color: '#64748b', fontSize: '0.8rem', marginTop: '0.2rem' }}>Exact or reworded</div>
            </div>

            <div className="admin-content-card" style={{ padding: '1.25rem' }}>
              <div style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.35rem' }}>Syllabus Exam Coverage</div>
              <div style={{ fontSize: '1.75rem', fontWeight: 700, color: coverageAvailable ? '#10b981' : '#94a3b8' }}>
                {coverageAvailable ? `${analysis.coverage_score}%` : 'Pending'}
              </div>
              {coverageAvailable ? (
                <div style={{ backgroundColor: 'rgba(255,255,255,0.1)', height: '5px', borderRadius: '3px', marginTop: '0.5rem', overflow: 'hidden' }}>
                  <div style={{ width: `${analysis.coverage_score}%`, height: '100%', backgroundColor: '#10b981' }} />
                </div>
              ) : (
                <div style={{ color: '#64748b', fontSize: '0.8rem', marginTop: '0.2rem' }}>Upload syllabus to compute</div>
              )}
            </div>
          </div>

          {analysis.papers && analysis.papers.length > 0 && (
            <div className="admin-content-card">
              <h2 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.35rem' }}>
                Paper Processing Status
              </h2>
              <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '1rem' }}>
                Every indexed paper is listed, including papers that have not been queued yet.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                {analysis.papers.map((paper) => (
                  <div key={paper.paper_id} style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', backgroundColor: 'rgba(30, 41, 59, 0.55)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '6px', padding: '0.7rem 0.9rem' }}>
                    <div>
                      <div style={{ color: '#f1f5f9', fontSize: '0.9rem', fontWeight: 600 }}>{paper.title}</div>
                      <div style={{ color: '#94a3b8', fontSize: '0.78rem' }}>
                        {paper.exam_type} {paper.examination_year || ''} {paper.cie_number ? `CIE ${paper.cie_number}` : ''} - {paper.question_count} questions ({paper.classified_count} classified)
                      </div>
                      {paper.error_message && <div style={{ color: '#fca5a5', fontSize: '0.78rem', marginTop: '0.2rem' }}>{paper.error_message}</div>}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      {getJobBadge(paper.job_status)}
                      <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>{paper.stage || ''}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="admin-content-card">
            <h2 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.35rem' }}>
              Unit-wise Marks & Question Distribution
            </h2>
            {syllabusStatus === 'PENDING' && (
              <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.75rem' }}>
                Official syllabus is not uploaded. Unit distribution will appear after syllabus ingestion.
              </p>
            )}
            {analysis.unit_stats.length === 0 ? (
              <EmptyState title="No Unit Data" description="Syllabus coverage is pending, so unit-wise weightage cannot be computed yet." />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                {analysis.unit_stats.map((u) => (
                  <div key={u.unit_number} style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                      <span style={{ fontWeight: 600, color: '#f1f5f9' }}>
                        Unit {u.unit_number}: {u.title}
                      </span>
                      <span style={{ color: '#94a3b8' }}>
                        {u.question_count} questions - {u.total_marks} marks ({u.marks_percentage}%)
                      </span>
                    </div>
                    <div style={{ backgroundColor: 'rgba(255,255,255,0.08)', height: '10px', borderRadius: '5px', overflow: 'hidden' }}>
                      <div style={{ width: `${Math.min(u.marks_percentage, 100)}%`, height: '100%', backgroundColor: '#6366f1', borderRadius: '5px' }} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="admin-content-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div>
                <h2 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#f8fafc' }}>Topic Importance & Exam Frequency</h2>
                <p style={{ color: '#94a3b8', fontSize: '0.85rem' }}>
                  Ranked by frequency, known marks, recency, and repeats. Priority is a historical signal, not a prediction.
                </p>
              </div>
            </div>

            {analysis.topic_insights.length === 0 ? (
              <EmptyState title="No Topics Discovered Yet" description="No readable questions were available to classify for this subject." />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {analysis.topic_insights.map((t) => {
                  const key = topicKey(t)
                  const learningStatus = t.learning_status || 'NOT_STARTED'
                  return (
                    <div key={key} style={{ backgroundColor: 'rgba(30, 41, 59, 0.6)', border: '1px solid rgba(255, 255, 255, 0.08)', borderRadius: '8px', padding: '1rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem' }}>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                            <span style={{ fontWeight: 600, color: '#f8fafc', fontSize: '1rem' }}>{t.topic_title}</span>
                            {getPriorityBadge(t.priority_category)}
                            {(t.provisional || syllabusStatus === 'PENDING') && (
                              <span style={{ backgroundColor: 'rgba(148, 163, 184, 0.15)', color: '#cbd5e1', fontSize: '0.7rem', padding: '0.2rem 0.4rem', borderRadius: '4px' }}>PROVISIONAL TOPIC</span>
                            )}
                          </div>
                          <div style={{ color: '#94a3b8', fontSize: '0.8rem', marginTop: '0.2rem' }}>
                            {t.unit_number ? `Unit ${t.unit_number} - ` : ''}Asked {t.frequency} times ({t.total_marks} known marks) - Last appeared {t.last_appeared_year || 'N/A'}
                          </div>
                          {t.why_important && <div style={{ color: '#64748b', fontSize: '0.78rem', marginTop: '0.3rem' }}>{t.why_important}</div>}
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#a855f7' }}>
                              {t.priority_score}<span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>/100</span>
                            </div>
                            <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Priority Index</div>
                          </div>

                          <select
                            aria-label={`Learning status for ${t.topic_title}`}
                            value={learningStatus}
                            disabled={savingTopic === key}
                            onChange={(e) => setTopicStatus(t, e.target.value)}
                            style={{ backgroundColor: '#0f172a', color: '#e2e8f0', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.35rem 0.5rem', fontSize: '0.78rem' }}
                          >
                            {LEARNING_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                          </select>

                          <button
                            type="button"
                            onClick={() => setExpandedTopic(expandedTopic === key ? null : key)}
                            className="content-btn is-secondary"
                            style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem' }}
                          >
                            {expandedTopic === key ? 'Hide Questions' : 'View Questions'}
                          </button>
                        </div>
                      </div>

                      {expandedTopic === key && t.sample_questions && t.sample_questions.length > 0 && (
                        <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                          <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#cbd5e1', marginBottom: '0.4rem' }}>
                            Historical Exam Questions:
                          </div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                            {t.sample_questions.map((sq, idx) => {
                              const isBookmarked = sq.question_id ? bookmarkedIds.has(sq.question_id) : false
                              return (
                                <div key={`${sq.question_number}-${idx}`} style={{ backgroundColor: 'rgba(15, 23, 42, 0.6)', padding: '0.5rem 0.75rem', borderRadius: '4px', fontSize: '0.85rem', color: '#e2e8f0', display: 'flex', justifyContent: 'space-between', gap: '0.75rem' }}>
                                  <div>
                                    <span style={{ color: '#60a5fa', fontWeight: 600, marginRight: '0.4rem' }}>
                                      Q{sq.question_number} {sq.year ? `(${sq.year})` : ''}:
                                    </span>
                                    {sq.text}
                                    {sq.marks && <span style={{ color: '#94a3b8', marginLeft: '0.5rem' }}>[{sq.marks}M]</span>}
                                  </div>
                                  {sq.question_id && (
                                    <button
                                      type="button"
                                      onClick={() => toggleBookmark(sq.question_id)}
                                      className="content-btn is-secondary"
                                      style={{ fontSize: '0.72rem', padding: '0.2rem 0.45rem', whiteSpace: 'nowrap', height: 'fit-content' }}
                                    >
                                      {isBookmarked ? 'Bookmarked' : 'Bookmark'}
                                    </button>
                                  )}
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <div className="admin-content-card">
            <h2 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.35rem' }}>
              Bookmarked PYQ Questions
            </h2>
            <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.75rem' }}>
              Your saved questions for focused revision.
            </p>
            {bookmarks.length === 0 ? (
              <EmptyState title="No Bookmarked Questions" description="Bookmark questions from the topic list to build a revision set." />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {bookmarks.map((question) => (
                  <div key={question.id} style={{ backgroundColor: 'rgba(30, 41, 59, 0.55)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '6px', padding: '0.7rem 0.9rem', display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
                    <div>
                      <div style={{ color: '#60a5fa', fontSize: '0.8rem', fontWeight: 600 }}>
                        Q{question.question_number} - {question.paper.title} {question.paper.examination_year || ''}
                      </div>
                      <div style={{ color: '#e2e8f0', fontSize: '0.85rem', marginTop: '0.2rem' }}>{question.extracted_text}</div>
                    </div>
                    <button type="button" onClick={() => toggleBookmark(question.id)} className="content-btn is-secondary" style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem', height: 'fit-content' }}>
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

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
                  <div key={idx} style={{ backgroundColor: 'rgba(30, 41, 59, 0.5)', border: '1px solid rgba(255, 255, 255, 0.08)', borderRadius: '8px', padding: '0.9rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                      <span style={{ color: '#34d399', fontSize: '0.8rem', fontWeight: 600 }}>
                        {c.repeat_category.replace(/_/g, ' ')} - {Math.round(c.similarity_score * 100)}% Match
                      </span>
                      {c.source_marks && <span style={{ color: '#94a3b8', fontSize: '0.8rem' }}>{c.source_marks} Marks</span>}
                    </div>
                    <div style={{ color: '#f1f5f9', fontSize: '0.9rem', marginBottom: '0.4rem' }}>&quot;{c.source_text}&quot;</div>
                    {c.explanation && <div style={{ color: '#64748b', fontSize: '0.75rem' }}>{c.explanation}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem' }}>
            <div className="admin-content-card">
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.75rem' }}>
                High-Return Topics (Study First)
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {analysis.recommendations?.study_first?.length ? (
                  analysis.recommendations.study_first.map((item, idx) => (
                    <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', backgroundColor: 'rgba(255,255,255,0.03)', padding: '0.6rem 0.8rem', borderRadius: '6px' }}>
                      <span style={{ color: '#e2e8f0', fontSize: '0.9rem' }}>
                        {idx + 1}. {item.topic_title} {item.unit_number ? `(Unit ${item.unit_number})` : ''}
                      </span>
                      <span style={{ color: '#a855f7', fontWeight: 600, fontSize: '0.85rem' }}>{item.priority_score} pts</span>
                    </div>
                  ))
                ) : (
                  <div style={{ color: '#94a3b8', fontSize: '0.85rem' }}>No topic recommendations yet.</div>
                )}
              </div>
            </div>

            <div className="admin-content-card">
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.75rem' }}>
                Syllabus Coverage Gaps
              </h3>
              {syllabusStatus === 'PENDING' ? (
                <div style={{ color: '#c7d2fe', fontSize: '0.85rem' }}>
                  Coverage gaps are pending because no official syllabus is uploaded. Provisional topics are not treated as official syllabus coverage.
                </div>
              ) : analysis.recommendations?.coverage_gaps?.length === 0 ? (
                <div style={{ color: '#10b981', fontSize: '0.85rem' }}>All syllabus topics have appeared in past exams.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {analysis.recommendations?.coverage_gaps?.slice(0, 5).map((gap, idx) => (
                    <div key={idx} style={{ backgroundColor: 'rgba(255,255,255,0.03)', padding: '0.6rem 0.8rem', borderRadius: '6px', fontSize: '0.85rem', color: '#cbd5e1' }}>
                      Unit {gap.unit_number}: <strong>{gap.topic_title}</strong>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {analysis.recommendations?.data_notes && analysis.recommendations.data_notes.length > 0 && (
            <div className="admin-content-card">
              <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.5rem' }}>Data Notes</h3>
              <ul style={{ margin: 0, paddingLeft: '1.2rem', color: '#94a3b8', fontSize: '0.82rem' }}>
                {analysis.recommendations.data_notes.map((note, idx) => (
                  <li key={idx}>{note}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
