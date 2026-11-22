interface StatCardProps {
  label: string
  value: number | string
  hint?: string
}

export default function StatCard({ label, value, hint }: StatCardProps) {
  return (
    <article className="stat-card">
      <p>{label}</p>
      <h3>{value}</h3>
      {hint && <span>{hint}</span>}
    </article>
  )
}
