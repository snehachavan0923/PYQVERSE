import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { errorDetail, getWithAuth } from '../services/authApi'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'

interface ResourceResponse {
  available: boolean
  resources: unknown[]
  count: number
  message: string
}

export default function StudentResources() {
  const { session } = useAuth()
  const [data, setData] = useState<ResourceResponse | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getWithAuth<ResourceResponse>('/auth/student/resources', session)
      .then(setData)
      .catch((err) => setError(errorDetail(err, 'Unable to load learning resources')))
  }, [session])

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Learning resources"
        title="Learning resources"
        description="Notes and supporting material uploaded for your subjects."
      />
      {error && <p className="form-error">{error}</p>}
      {!data && !error && <div className="pyq-loading">Loading learning resources...</div>}
      {data && (
        <EmptyState
          title="No resources uploaded yet"
          description={data.message || 'Learning resources will appear here once they are uploaded by faculty.'}
        />
      )}
    </section>
  )
}
