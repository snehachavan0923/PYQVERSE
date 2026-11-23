export default function StudentContentPage({ kind }: { kind: 'syllabus' | 'pyqs' | 'resources' }) {
  const title = kind === 'syllabus' ? 'Syllabus' : kind === 'pyqs' ? 'Previous year questions' : 'Learning resources'
  return (
    <section className="dashboard-shell">
      <header className="dashboard-header"><div><p className="eyebrow">Academic content</p><h1>{title}</h1></div></header>
      <article className="dashboard-card wide"><p className="muted">No published content is available in this phase.</p></article>
    </section>
  )
}
