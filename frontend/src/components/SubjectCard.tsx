import { Link } from 'react-router-dom'
import type { SubjectSummary } from '../types/dashboard'

function StatusPill({ available, label }: { available: boolean; label: string }) {
  return (
    <span className={`status-pill${available ? ' status-available' : ' status-empty'}`}>
      {label}: {available ? 'Available' : 'Not uploaded'}
    </span>
  )
}

export default function SubjectCard({ subject }: { subject: SubjectSummary }) {
  return (
    <Link className="subject-card-link" to={`/student/subjects/${subject.id}`} aria-label={`Open ${subject.code} ${subject.name}`}>
      <article className="subject-card">
        <div className="subject-card-head">
          <div>
            <p className="eyebrow">{subject.code}</p>
            <h3>{subject.name}</h3>
          </div>
          <span className="type-pill">{subject.subject_type}</span>
        </div>
        <div className="subject-meta">
          <span>{subject.semester ?? 'Semester not set'}</span>
          {subject.credits !== null && <span>{subject.credits} credits</span>}
        </div>
        <div className="status-list">
          <StatusPill available={subject.syllabus_available} label="Syllabus" />
          <StatusPill available={subject.pyq_available} label="PYQs" />
          <StatusPill available={subject.learning_resources_available} label="Resources" />
        </div>
        <div className="subject-counts">
          <span>{subject.pyq_count} previous year question papers</span>
          <span>{subject.learning_resource_count} learning resources</span>
        </div>
      </article>
    </Link>
  )
}
