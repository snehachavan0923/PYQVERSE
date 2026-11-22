import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'

interface AdminPlaceholderProps {
  title: string
  description: string
}

export default function AdminPlaceholder({ title, description }: AdminPlaceholderProps) {
  return (
    <section className="dashboard-page">
      <PageHeader eyebrow="Content management" title={title} description={description} />
      <EmptyState
        title="No content uploaded yet"
        description="This section is ready for future document uploads. No upload or processing workflow is active in Phase 4."
      />
    </section>
  )
}
