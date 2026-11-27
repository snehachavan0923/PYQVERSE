import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail } from '../services/authApi'
import {
  listAnalysisJobs,
  getAnalysisOverview,
  syncAnalysisJobs,
  retryAnalysisJob,
  listFlaggedQuestions,
  correctQuestion,
  type AnalysisJobItem,
  type AnalysisOverview,
  type FlaggedQuestionItem,
} from '../services/analysisApi'
import notifications from '../services/notification'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import { LoadingState, ErrorState } from '../components/PageState'

export default function AdminAnalysis() {
  const { session } = useAuth()
  const [activeTab, setActiveTab] = useState<'jobs' | 'flagged'>('jobs')
  const [jobs, setJobs] = useState<AnalysisJobItem[] | null>(null)
  const [flagged, setFlagged] = useState<FlaggedQuestionItem[] | null>(null)
  const [overview, setOverview] = useState<AnalysisOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retryingId, setRetryingId] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)

  // Review modal state
  const [selectedQuestion, setSelectedQuestion] = useState<FlaggedQuestionItem | null>(null)
  const [editMainTopic, setEditMainTopic] = useState('')
  const [editSubtopic, setEditSubtopic] = useState('')
  const [editUnitNumber, setEditUnitNumber] = useState<number>(1)
  const [editMarks, setEditMarks] = useState<number>(10)
  const [savingAction, setSavingAction] = useState(false)

  const loadData = useCallback(() => {
    setLoading(true)
    setError('')

    const overviewPromise =
      typeof getAnalysisOverview === 'function'
        ? getAnalysisOverview(session).catch(() => null)
        : Promise.resolve(null)

    Promise.all([
      listAnalysisJobs(session),
      listFlaggedQuestions(session),
      overviewPromise,
    ])
      .then(([jobsRes, flaggedRes, overviewRes]) => {
        setJobs(jobsRes.items)
        setFlagged(flaggedRes.items)
        setOverview(overviewRes)
      })
      .catch((err) => setError(errorDetail(err, 'Failed to load analysis data')))
      .finally(() => setLoading(false))
  }, [session])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleSync = async () => {
    setSyncing(true)
    try {
      if (typeof syncAnalysisJobs === 'function') {
        const result = await syncAnalysisJobs(session, { run: true, force: false })
        notifications.success(
          `Queued ${result.created} new job(s), reset ${result.reset}, skipped ${result.skipped}`,
        )
      }
      loadData()
    } catch (err) {
      notifications.error(errorDetail(err, 'Failed to queue missing analysis jobs'))
    } finally {
      setSyncing(false)
    }
  }

  const handleRetry = async (jobId: string) => {
    setRetryingId(jobId)
    try {
      await retryAnalysisJob(session, jobId)
      notifications.success('Analysis job scheduled for retry')
      loadData()
    } catch (err) {
      notifications.error(errorDetail(err, 'Failed to retry job'))
    } finally {
      setRetryingId(null)
    }
  }

  const openReviewModal = (q: FlaggedQuestionItem) => {
    setSelectedQuestion(q)
    setEditMainTopic(q.classification?.main_topic || '')
    setEditSubtopic(q.classification?.subtopic || '')
    setEditUnitNumber(q.classification?.unit_number || 1)
    setEditMarks(q.marks || 10)
  }

  const closeReviewModal = () => {
    setSelectedQuestion(null)
    setSavingAction(false)
  }

  const handleQuestionAction = async (action: 'APPROVE' | 'REJECT' | 'UPDATE') => {
    if (!selectedQuestion) return
    setSavingAction(true)
    try {
      await correctQuestion(session, selectedQuestion.id, {
        main_topic: editMainTopic.trim() || undefined,
        subtopic: editSubtopic.trim() || undefined,
        unit_number: Number(editUnitNumber) || undefined,
        marks: Number(editMarks) || undefined,
        action,
      })
      notifications.success(
        action === 'APPROVE'
          ? 'Question verified and approved'
          : action === 'REJECT'
          ? 'Question rejected'
          : 'Question classification updated'
      )
      closeReviewModal()
      loadData()
    } catch (err) {
      notifications.error(errorDetail(err, `Failed to ${action.toLowerCase()} question`))
    } finally {
      setSavingAction(false)
    }
  }

  const getStatusBadge = (status: AnalysisJobItem['status']) => {
    switch (status) {
      case 'COMPLETED':
        return <span className="admin-status-badge is-verified">Completed</span>
      case 'FLAGGED_REVIEW':
        return <span className="admin-status-badge is-pending">Needs Review</span>
      case 'FAILED':
        return <span className="admin-status-badge is-rejected">Failed</span>
      case 'EXTRACTING':
      case 'CLASSIFYING':
      case 'MAPPING':
      case 'ANALYZING':
        return <span className="admin-status-badge is-draft">{status}</span>
      case 'PENDING':
      default:
        return <span className="admin-status-badge is-draft">Queued</span>
    }
  }

  if (loading && !jobs && !flagged) {
    return (
      <section className="dashboard-page">
        <PageHeader eyebrow="AI Intelligence Engine" title="Automated PYQ Analysis" />
        <LoadingState label="Loading analysis dashboard..." />
      </section>
    )
  }

  if (error && !jobs && !flagged) {
    return (
      <section className="dashboard-page">
        <PageHeader eyebrow="AI Intelligence Engine" title="Automated PYQ Analysis" />
        <ErrorState message={error} onRetry={loadData} />
      </section>
    )
  }

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="AI Intelligence Engine"
        title="Automated PYQ Analysis"
        description="Monitor automated background processing of question papers, review model confidence, and calibrate uncertain mappings."
      />

      {overview && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1.5rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.75rem' }}>
            {[
              { label: 'Indexed papers', value: overview.total_documents },
              { label: 'Never queued', value: overview.documents_without_jobs, warn: overview.documents_without_jobs > 0 },
              { label: 'Questions extracted', value: overview.extracted_questions },
              { label: 'Questions classified', value: overview.classified_questions },
              { label: 'Failed jobs', value: overview.failed_jobs, warn: overview.failed_jobs > 0 },
              { label: 'Flagged jobs', value: overview.flagged_jobs, warn: overview.flagged_jobs > 0 },
            ].map((card) => (
              <div key={card.label} className="admin-content-card" style={{ padding: '0.9rem 1rem' }}>
                <div style={{ color: '#94a3b8', fontSize: '0.78rem' }}>{card.label}</div>
                <div style={{ color: card.warn ? '#f59e0b' : '#f8fafc', fontSize: '1.45rem', fontWeight: 700 }}>{card.value}</div>
              </div>
            ))}
          </div>

          {overview.documents_without_jobs > 0 && (
            <div style={{ backgroundColor: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: '8px', padding: '0.85rem 1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
              <div style={{ color: '#fde68a', fontSize: '0.88rem' }}>
                <strong>{overview.documents_without_jobs} indexed paper(s) have no analysis job.</strong>{' '}
                These papers were uploaded before automatic processing was enabled.
              </div>
              <button type="button" onClick={handleSync} disabled={syncing} className="content-btn is-primary" style={{ padding: '0.4rem 0.8rem', fontSize: '0.82rem' }}>
                {syncing ? 'Queueing...' : 'Analyse Missing Papers'}
              </button>
            </div>
          )}

          {overview.papers.filter((paper) => paper.job_status === 'NOT_QUEUED').length > 0 && (
            <div className="admin-content-card" style={{ padding: '0.9rem 1rem' }}>
              <div style={{ color: '#cbd5e1', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.4rem' }}>Not queued</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                {overview.papers
                  .filter((paper) => paper.job_status === 'NOT_QUEUED')
                  .map((paper) => (
                    <div key={paper.paper_id} style={{ color: '#94a3b8', fontSize: '0.8rem' }}>
                      {paper.subject_code ? `[${paper.subject_code}] ` : ''}
                      {paper.title} - {paper.question_count} stored questions
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', borderBottom: '1px solid rgba(255, 255, 255, 0.1)', paddingBottom: '0.75rem' }}>
        <button
          type="button"
          onClick={() => setActiveTab('jobs')}
          className={`filter-chip ${activeTab === 'jobs' ? 'is-active' : ''}`}
          style={{ padding: '0.5rem 1rem', fontSize: '0.95rem' }}
        >
          Analysis Pipeline Jobs ({jobs?.length ?? 0})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('flagged')}
          className={`filter-chip ${activeTab === 'flagged' ? 'is-active' : ''}`}
          style={{ padding: '0.5rem 1rem', fontSize: '0.95rem' }}
        >
          Flagged for Review ({flagged?.length ?? 0})
        </button>
      </div>

      {activeTab === 'jobs' && (
        <div className="admin-content-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#f8fafc' }}>Paper Analysis Pipeline</h2>
            <button type="button" onClick={loadData} className="content-btn is-secondary" style={{ padding: '0.4rem 0.8rem' }}>
              Refresh Jobs
            </button>
          </div>

          {!jobs || jobs.length === 0 ? (
            <EmptyState
              title="No Analysis Jobs Found"
              description="Upload a Previous Year Question Paper in PYQ Management to automatically trigger the analysis pipeline."
            />
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', color: '#94a3b8' }}>
                    <th style={{ padding: '0.75rem' }}>Paper & Subject</th>
                    <th style={{ padding: '0.75rem' }}>Status & Stage</th>
                    <th style={{ padding: '0.75rem' }}>Progress</th>
                    <th style={{ padding: '0.75rem' }}>Questions</th>
                    <th style={{ padding: '0.75rem' }}>Avg Conf</th>
                    <th style={{ padding: '0.75rem' }}>Engine</th>
                    <th style={{ padding: '0.75rem', textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((j) => (
                    <tr key={j.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <td style={{ padding: '0.75rem' }}>
                        <div style={{ fontWeight: 600, color: '#f1f5f9' }}>{j.title}</div>
                        <div style={{ color: '#94a3b8', fontSize: '0.8rem' }}>
                          {j.subject_code ? `${j.subject_code} • ` : ''}{j.exam_type} {j.examination_year}
                        </div>
                      </td>
                      <td style={{ padding: '0.75rem' }}>
                        <div>{getStatusBadge(j.status)}</div>
                        <div style={{ color: '#cbd5e1', fontSize: '0.8rem', marginTop: '0.25rem' }}>{j.stage || '—'}</div>
                      </td>
                      <td style={{ padding: '0.75rem', minWidth: '120px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <div style={{ flex: 1, backgroundColor: 'rgba(255,255,255,0.1)', height: '6px', borderRadius: '3px', overflow: 'hidden' }}>
                            <div
                              style={{
                                width: `${j.progress_percent}%`,
                                height: '100%',
                                backgroundColor: j.status === 'FAILED' ? '#ef4444' : j.status === 'COMPLETED' ? '#10b981' : '#6366f1',
                              }}
                            />
                          </div>
                          <span style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>{j.progress_percent}%</span>
                        </div>
                      </td>
                      <td style={{ padding: '0.75rem', color: '#cbd5e1' }}>
                        <div>{j.total_questions} total</div>
                        {j.flagged_questions > 0 && (
                          <div style={{ color: '#f59e0b', fontSize: '0.75rem' }}>{j.flagged_questions} flagged</div>
                        )}
                      </td>
                      <td style={{ padding: '0.75rem', color: '#cbd5e1' }}>
                        {j.average_confidence !== null ? `${Math.round(j.average_confidence * 100)}%` : '—'}
                      </td>
                      <td style={{ padding: '0.75rem', color: '#94a3b8', fontSize: '0.8rem' }}>
                        {j.model_name || 'Rule/NLP'}
                      </td>
                      <td style={{ padding: '0.75rem', textAlign: 'right' }}>
                        {(j.status === 'FAILED' || j.status === 'FLAGGED_REVIEW' || j.status === 'COMPLETED') && (
                          <button
                            type="button"
                            onClick={() => handleRetry(j.id)}
                            disabled={retryingId === j.id}
                            className="content-btn is-secondary"
                            style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem' }}
                          >
                            {retryingId === j.id ? 'Starting...' : 'Re-run'}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 'flagged' && (
        <div className="admin-content-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#f8fafc' }}>Review Flagged Mappings</h2>
              <p style={{ color: '#94a3b8', fontSize: '0.85rem' }}>
                Questions with confidence below threshold (&lt;65%) or provisional syllabus associations.
              </p>
            </div>
            <button type="button" onClick={loadData} className="content-btn is-secondary" style={{ padding: '0.4rem 0.8rem' }}>
              Refresh
            </button>
          </div>

          {!flagged || flagged.length === 0 ? (
            <EmptyState
              title="All Questions Verified"
              description="There are currently no uncertain question classifications requiring manual calibration."
            />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {flagged.map((q) => (
                <div
                  key={q.id}
                  style={{
                    backgroundColor: 'rgba(30, 41, 59, 0.7)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '8px',
                    padding: '1rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                    <div>
                      <span style={{ fontWeight: 600, color: '#60a5fa', marginRight: '0.5rem' }}>Q{q.question_number}</span>
                      <span style={{ color: '#cbd5e1', fontSize: '0.85rem' }}>
                        {q.subject_code ? `[${q.subject_code}] ` : ''}{q.paper_title}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.8rem', color: '#f59e0b', backgroundColor: 'rgba(245, 158, 11, 0.15)', padding: '0.2rem 0.5rem', borderRadius: '4px' }}>
                        Conf: {q.classification?.confidence ? `${Math.round(q.classification.confidence * 100)}%` : 'Low'}
                      </span>
                      {q.marks !== null && (
                        <span style={{ fontSize: '0.8rem', color: '#cbd5e1', backgroundColor: 'rgba(255, 255, 255, 0.1)', padding: '0.2rem 0.5rem', borderRadius: '4px' }}>
                          {q.marks} Marks
                        </span>
                      )}
                    </div>
                  </div>

                  <p style={{ color: '#f1f5f9', fontSize: '0.95rem', margin: '0.5rem 0', lineHeight: 1.5 }}>
                    {q.extracted_text}
                  </p>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.75rem', paddingTop: '0.5rem', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ fontSize: '0.85rem', color: '#94a3b8' }}>
                      Suggested Unit {q.classification?.unit_number || '?'}: <strong>{q.classification?.main_topic || 'Unmapped'}</strong>
                      {q.classification?.explanation && (
                        <div style={{ fontSize: '0.8rem', color: '#64748b', marginTop: '0.2rem' }}>
                          Reason: {q.classification.explanation}
                        </div>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={() => openReviewModal(q)}
                      className="content-btn is-primary"
                      style={{ padding: '0.35rem 0.8rem', fontSize: '0.85rem' }}
                    >
                      Calibrate & Approve
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Review & Correction Modal */}
      {selectedQuestion && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
        >
          <div
            style={{
              backgroundColor: '#0f172a',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              borderRadius: '12px',
              padding: '1.5rem',
              maxWidth: '600px',
              width: '100%',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
            }}
          >
            <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.5rem' }}>
              Calibrate Question Q{selectedQuestion.question_number}
            </h3>
            <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '1rem' }}>
              Adjust unit and topic classification or confirm model suggestions.
            </p>

            <div style={{ backgroundColor: 'rgba(30, 41, 59, 0.5)', padding: '0.75rem', borderRadius: '6px', marginBottom: '1rem', maxHeight: '120px', overflowY: 'auto' }}>
              <div style={{ color: '#cbd5e1', fontSize: '0.9rem', fontStyle: 'italic' }}>
                "{selectedQuestion.extracted_text}"
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <label style={{ display: 'block', color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.3rem' }}>
                  Unit Number (1-5)
                </label>
                <input
                  type="number"
                  min={1}
                  max={6}
                  value={editUnitNumber}
                  onChange={(e) => setEditUnitNumber(Number(e.target.value))}
                  style={{
                    width: '100%',
                    backgroundColor: '#1e293b',
                    border: '1px solid rgba(255,255,255,0.15)',
                    borderRadius: '6px',
                    padding: '0.5rem',
                    color: '#f8fafc',
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.3rem' }}>
                  Assigned Marks
                </label>
                <input
                  type="number"
                  min={1}
                  max={30}
                  value={editMarks}
                  onChange={(e) => setEditMarks(Number(e.target.value))}
                  style={{
                    width: '100%',
                    backgroundColor: '#1e293b',
                    border: '1px solid rgba(255,255,255,0.15)',
                    borderRadius: '6px',
                    padding: '0.5rem',
                    color: '#f8fafc',
                  }}
                />
              </div>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.3rem' }}>
                Main Topic
              </label>
              <input
                type="text"
                value={editMainTopic}
                onChange={(e) => setEditMainTopic(e.target.value)}
                placeholder="e.g. Memory Architecture, Sorting Algorithms"
                style={{
                  width: '100%',
                  backgroundColor: '#1e293b',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: '6px',
                  padding: '0.5rem',
                  color: '#f8fafc',
                }}
              />
            </div>

            <div style={{ marginBottom: '1.5rem' }}>
              <label style={{ display: 'block', color: '#94a3b8', fontSize: '0.85rem', marginBottom: '0.3rem' }}>
                Subtopic / Concepts
              </label>
              <input
                type="text"
                value={editSubtopic}
                onChange={(e) => setEditSubtopic(e.target.value)}
                placeholder="e.g. SRAM vs DRAM"
                style={{
                  width: '100%',
                  backgroundColor: '#1e293b',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: '6px',
                  padding: '0.5rem',
                  color: '#f8fafc',
                }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                type="button"
                onClick={closeReviewModal}
                disabled={savingAction}
                className="content-btn is-secondary"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleQuestionAction('REJECT')}
                disabled={savingAction}
                className="content-btn is-danger"
              >
                Reject
              </button>
              <button
                type="button"
                onClick={() => handleQuestionAction('APPROVE')}
                disabled={savingAction}
                className="content-btn is-primary"
              >
                {savingAction ? 'Saving...' : 'Verify & Approve'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
