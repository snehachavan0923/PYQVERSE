export default function Home() {
  return (
    <section className="flex flex-col items-center gap-4 text-center">
      <span className="eyebrow">Academic workspace</span>
      <h1 className="text-4xl font-semibold tracking-tight text-[var(--text)] sm:text-5xl">
        PYQVERSE
      </h1>
      <p className="text-base font-medium text-[var(--primary)]">
        Your previous year questions, organised.
      </p>
      <p className="max-w-md text-sm text-[var(--text-secondary)]">
        A focused workspace for syllabus, question papers and learning resources.
      </p>
    </section>
  )
}
