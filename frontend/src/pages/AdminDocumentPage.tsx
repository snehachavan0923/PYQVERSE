export default function AdminDocumentPage({ kind }: { kind: 'syllabus' | 'pyqs' | 'resources' | 'uploads' }) {
  const title = kind === 'uploads' ? 'Uploads' : kind === 'pyqs' ? 'PYQ papers' : kind === 'resources' ? 'Learning resources' : 'Syllabus'
  return (
    <section className="dashboard-shell">
      <header className="dashboard-header"><div><p className="eyebrow">Content management</p><h1>{title}</h1></div></header>
      <article className="dashboard-card wide">
        <h2>No {title.toLowerCase()} workflow is published yet</h2>
        <p className="muted">The secure upload workflow is deferred until storage buckets and document metadata are configured. This page does not fabricate content.</p>
      </article>
    </section>
  )
}
