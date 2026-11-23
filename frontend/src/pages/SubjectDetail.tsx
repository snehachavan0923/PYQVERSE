import { useParams } from 'react-router-dom'

export default function SubjectDetail() {
  const { subjectId } = useParams()
  return (
    <section className="dashboard-shell">
      <header className="dashboard-header"><div><p className="eyebrow">Subject</p><h1>Subject details</h1></div></header>
      <article className="dashboard-card wide"><p className="muted">Subject detail is not yet published. Requested ID: {subjectId}</p></article>
    </section>
  )
}
