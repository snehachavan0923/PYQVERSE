import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { deleteWithAuth, errorDetail, getWithAuth, patchWithAuth, postWithAuth } from '../services/authApi'
import notifications from '../services/notification'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import { LoadingState, ErrorState } from '../components/PageState'

interface BranchItem { id: string; name: string; code: string; active: boolean }
interface SchemeItem { id: string; name: string; code: string; active: boolean }
interface SemesterItem { id: string; number: number; name: string; active: boolean; academic_scheme_id: string }
interface SubjectItem {
  id: string
  code: string
  name: string
  subject_type: string
  credits: number | null
  description: string | null
  semester_id: string
  academic_scheme_id: string
  active: boolean
}
interface BasketItem { id: string; name: string; academic_scheme_id: string; semester_id: string; active: boolean }
interface ElectiveItem {
  basket_id: string
  basket_name: string
  academic_scheme_id: string
  semester_id: string
  subject_id: string
  subject_code: string
  subject_name: string
  active: boolean
}

type Tab = 'branches' | 'schemes' | 'semesters' | 'subjects' | 'electives'

const TABS: { key: Tab; label: string }[] = [
  { key: 'branches', label: 'Branches' },
  { key: 'schemes', label: 'Schemes' },
  { key: 'semesters', label: 'Semesters' },
  { key: 'subjects', label: 'Subjects' },
  { key: 'electives', label: 'Electives' },
]

const emptyBranch = { name: '', code: '' }
const emptyScheme = { name: '', code: '' }
const emptySemester = { academic_scheme_id: '', number: 1, name: '' }
const emptySubject = { academic_scheme_id: '', semester_id: '', code: '', name: '', subject_type: 'CORE', credits: '', description: '', active: true }
const emptyBasket = { academic_scheme_id: '', semester_id: '', name: '' }

export default function AdminAcademic() {
  const { session } = useAuth()
  const [tab, setTab] = useState<Tab>('branches')
  const [branches, setBranches] = useState<BranchItem[]>([])
  const [schemes, setSchemes] = useState<SchemeItem[]>([])
  const [semesters, setSemesters] = useState<SemesterItem[]>([])
  const [subjects, setSubjects] = useState<SubjectItem[]>([])
  const [baskets, setBaskets] = useState<BasketItem[]>([])
  const [electives, setElectives] = useState<ElectiveItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')

  const [branchForm, setBranchForm] = useState(emptyBranch)
  const [editingBranch, setEditingBranch] = useState<string | null>(null)
  const [schemeForm, setSchemeForm] = useState(emptyScheme)
  const [editingScheme, setEditingScheme] = useState<string | null>(null)
  const [semesterForm, setSemesterForm] = useState(emptySemester)
  const [editingSemester, setEditingSemester] = useState<string | null>(null)
  const [subjectForm, setSubjectForm] = useState(emptySubject)
  const [editingSubject, setEditingSubject] = useState<string | null>(null)
  const [basketForm, setBasketForm] = useState(emptyBasket)
  const [optionForm, setOptionForm] = useState({ basket_id: '', subject_id: '' })

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    Promise.all([
      getWithAuth<BranchItem[]>('/admin/academic/branches', session),
      getWithAuth<SchemeItem[]>('/admin/academic/schemes', session),
      getWithAuth<SemesterItem[]>('/admin/academic/semesters', session),
      getWithAuth<SubjectItem[]>('/admin/academic/subjects', session),
      getWithAuth<BasketItem[]>('/admin/academic/elective-baskets', session),
      getWithAuth<ElectiveItem[]>('/admin/academic/elective-options', session),
    ])
      .then(([branchRows, schemeRows, semesterRows, subjectRows, basketRows, optionRows]) => {
        setBranches(branchRows)
        setSchemes(schemeRows)
        setSemesters(semesterRows)
        setSubjects(subjectRows)
        setBaskets(basketRows)
        setElectives(optionRows)
        if (!semesterForm.academic_scheme_id && schemeRows[0]) {
          setSemesterForm((current) => ({ ...current, academic_scheme_id: schemeRows[0].id }))
        }
        if (!subjectForm.academic_scheme_id && schemeRows[0]) {
          const firstSemester = semesterRows.find((item) => item.academic_scheme_id === schemeRows[0].id)
          setSubjectForm((current) => ({
            ...current,
            academic_scheme_id: schemeRows[0].id,
            semester_id: firstSemester?.id ?? '',
          }))
        }
        if (!basketForm.academic_scheme_id && schemeRows[0]) {
          const firstSemester = semesterRows.find((item) => item.academic_scheme_id === schemeRows[0].id)
          setBasketForm((current) => ({
            ...current,
            academic_scheme_id: schemeRows[0].id,
            semester_id: firstSemester?.id ?? '',
          }))
        }
      })
      .catch((err) => setError(errorDetail(err, 'Unable to load academic catalog')))
      .finally(() => setLoading(false))
    // Form defaults are intentionally only seeded from the first load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session])

  useEffect(() => {
    load()
  }, [load])

  const semesterOptions = (schemeId: string) => semesters.filter((item) => item.academic_scheme_id === schemeId)
  const electiveSubjects = (schemeId: string, semesterId: string) =>
    subjects.filter((item) => item.subject_type === 'ELECTIVE' && item.academic_scheme_id === schemeId && item.semester_id === semesterId)

  const run = async (action: () => Promise<unknown>, success: string) => {
    if (saving) return
    setSaving(true)
    setFormError('')
    try {
      await action()
      void notifications.toast('success', success)
      load()
    } catch (err) {
      const message = errorDetail(err, 'The change could not be saved')
      setFormError(message)
      void notifications.error('Change not saved', message)
    } finally {
      setSaving(false)
    }
  }

  const confirmDeactivate = async (label: string, action: () => Promise<unknown>) => {
    const confirmed = await notifications.confirm({
      title: `Deactivate ${label}?`,
      text: 'Historical records are preserved. This item will no longer be available for new selections.',
      confirmText: 'Deactivate',
    })
    if (!confirmed) return
    await run(action, `${label} deactivated`)
  }

  const removeOption = async (basketId: string, subjectId: string, code: string) => {
    const confirmed = await notifications.confirm({
      title: `Remove ${code}?`,
      text: 'This subject will no longer be offered as an option in the basket.',
      confirmText: 'Remove option',
    })
    if (!confirmed) return
    await run(
      () => deleteWithAuth(`/admin/academic/elective-options/${basketId}/${subjectId}`, session),
      'Elective option removed',
    )
  }

  const submitBranch = (event: FormEvent) => {
    event.preventDefault()
    const body = { name: branchForm.name.trim(), code: branchForm.code.trim() }
    void run(
      () => (editingBranch
        ? patchWithAuth(`/admin/academic/branches/${editingBranch}`, session, body)
        : postWithAuth('/admin/academic/branches', session, body)),
      editingBranch ? 'Branch updated' : 'Branch created',
    ).then(() => {
      setBranchForm(emptyBranch)
      setEditingBranch(null)
    })
  }

  const submitScheme = (event: FormEvent) => {
    event.preventDefault()
    const body = { name: schemeForm.name.trim(), code: schemeForm.code.trim() }
    void run(
      () => (editingScheme
        ? patchWithAuth(`/admin/academic/schemes/${editingScheme}`, session, body)
        : postWithAuth('/admin/academic/schemes', session, body)),
      editingScheme ? 'Academic scheme updated' : 'Academic scheme created',
    ).then(() => {
      setSchemeForm(emptyScheme)
      setEditingScheme(null)
    })
  }

  const submitSemester = (event: FormEvent) => {
    event.preventDefault()
    const body = {
      academic_scheme_id: semesterForm.academic_scheme_id,
      number: Number(semesterForm.number),
      name: semesterForm.name.trim(),
    }
    void run(
      () => (editingSemester
        ? patchWithAuth(`/admin/academic/semesters/${editingSemester}`, session, {
            number: body.number,
            name: body.name,
          })
        : postWithAuth('/admin/academic/semesters', session, body)),
      editingSemester ? 'Semester updated' : 'Semester created',
    ).then(() => {
      setSemesterForm({ ...emptySemester, academic_scheme_id: semesterForm.academic_scheme_id })
      setEditingSemester(null)
    })
  }

  const submitSubject = (event: FormEvent) => {
    event.preventDefault()
    const body: Record<string, unknown> = {
      academic_scheme_id: subjectForm.academic_scheme_id,
      semester_id: subjectForm.semester_id,
      code: subjectForm.code.trim().toUpperCase(),
      name: subjectForm.name.trim(),
      subject_type: subjectForm.subject_type,
      credits: subjectForm.credits === '' ? null : Number(subjectForm.credits),
      description: subjectForm.description.trim() || null,
      active: subjectForm.active,
    }
    if (editingSubject) delete body.academic_scheme_id
    void run(
      () => (editingSubject
        ? patchWithAuth(`/admin/academic/subjects/${editingSubject}`, session, body)
        : postWithAuth('/admin/academic/subjects', session, body)),
      editingSubject ? 'Subject updated' : 'Subject created',
    ).then(() => {
      setSubjectForm({ ...emptySubject, academic_scheme_id: subjectForm.academic_scheme_id, semester_id: semesterOptions(subjectForm.academic_scheme_id)[0]?.id ?? '' })
      setEditingSubject(null)
    })
  }

  const submitBasket = (event: FormEvent) => {
    event.preventDefault()
    void run(
      () => postWithAuth('/admin/academic/elective-baskets', session, {
        academic_scheme_id: basketForm.academic_scheme_id,
        semester_id: basketForm.semester_id,
        name: basketForm.name.trim(),
      }),
      'Elective basket created',
    ).then(() => setBasketForm({ ...emptyBasket, academic_scheme_id: basketForm.academic_scheme_id, semester_id: basketForm.semester_id }))
  }

  const submitOption = (event: FormEvent) => {
    event.preventDefault()
    void run(
      () => postWithAuth('/admin/academic/elective-options', session, optionForm),
      'Elective option added',
    ).then(() => setOptionForm({ basket_id: '', subject_id: '' }))
  }

  const startEditBranch = (item: BranchItem) => {
    setEditingBranch(item.id)
    setBranchForm({ name: item.name, code: item.code })
    setFormError('')
  }
  const startEditScheme = (item: SchemeItem) => {
    setEditingScheme(item.id)
    setSchemeForm({ name: item.name, code: item.code })
    setFormError('')
  }
  const startEditSemester = (item: SemesterItem) => {
    setEditingSemester(item.id)
    setSemesterForm({ academic_scheme_id: item.academic_scheme_id, number: item.number, name: item.name })
    setFormError('')
  }
  const startEditSubject = (item: SubjectItem) => {
    setEditingSubject(item.id)
    setSubjectForm({
      academic_scheme_id: item.academic_scheme_id,
      semester_id: item.semester_id,
      code: item.code,
      name: item.name,
      subject_type: item.subject_type,
      credits: item.credits === null ? '' : String(item.credits),
      description: item.description ?? '',
      active: item.active,
    })
    setFormError('')
  }

  const selectedOptionBasket = baskets.find((item) => item.id === optionForm.basket_id)

  return (
    <section className="dashboard-page">
      <PageHeader
        eyebrow="Academic management"
        title="Academic catalog"
        description="Create and maintain branches, schemes, semesters, subjects and elective options. Deactivation never deletes historical records."
      />
      <div className="tab-bar" role="tablist" aria-label="Academic sections">
        {TABS.map((item) => (
          <button
            key={item.key}
            id={`tab-${item.key}`}
            type="button"
            role="tab"
            aria-selected={tab === item.key}
            aria-controls={`panel-${item.key}`}
            className={`tab-button${tab === item.key ? ' active' : ''}`}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error && <ErrorState message={error} onRetry={load} />}
      {loading && !branches.length && !schemes.length && <LoadingState label="Loading academic catalog" rows={3} />}

      {formError && <p className="form-error">{formError}</p>}

      {tab === 'branches' && (
        <div role="tabpanel" id="panel-branches" aria-labelledby="tab-branches" tabIndex={0}>
          <div className="two-column-grid">
            <form className="editor-panel" onSubmit={submitBranch}>
              <h2>{editingBranch ? 'Edit branch' : 'New branch'}</h2>
              <label>Name<input value={branchForm.name} onChange={(event) => setBranchForm({ ...branchForm, name: event.target.value })} required minLength={2} /></label>
              <label>Code<input value={branchForm.code} onChange={(event) => setBranchForm({ ...branchForm, code: event.target.value })} required /></label>
              <div className="form-actions">
                <button className="primary-button compact-button" disabled={saving}>{editingBranch ? 'Save changes' : 'Create branch'}</button>
                {editingBranch && <button className="secondary-button compact-button" type="button" onClick={() => { setEditingBranch(null); setBranchForm(emptyBranch) }}>Cancel</button>}
              </div>
            </form>
            <article className="table-card">
              <h2>Branches</h2>
              {branches.length ? <table><thead><tr><th>Code</th><th>Name</th><th>Status</th><th /></tr></thead><tbody>
                {branches.map((item) => <tr key={item.id}><td><strong>{item.code}</strong></td><td>{item.name}</td><td>{item.active ? 'Active' : 'Inactive'}</td><td className="table-actions"><button className="text-button" type="button" onClick={() => startEditBranch(item)}>Edit</button>{item.active && <button className="text-button danger-text" type="button" onClick={() => void confirmDeactivate('branch', () => deleteWithAuth(`/admin/academic/branches/${item.id}`, session))}>Deactivate</button>}</td></tr>)}
              </tbody></table> : <EmptyState title="No branches" description="Create the first branch." />}
            </article>
          </div>
        </div>
      )}

      {tab === 'schemes' && (
        <div role="tabpanel" id="panel-schemes" aria-labelledby="tab-schemes" tabIndex={0}>
          <div className="two-column-grid">
            <form className="editor-panel" onSubmit={submitScheme}>
              <h2>{editingScheme ? 'Edit scheme' : 'New scheme'}</h2>
              <label>Name<input value={schemeForm.name} onChange={(event) => setSchemeForm({ ...schemeForm, name: event.target.value })} required minLength={2} /></label>
              <label>Code<input value={schemeForm.code} onChange={(event) => setSchemeForm({ ...schemeForm, code: event.target.value })} required /></label>
              <div className="form-actions">
                <button className="primary-button compact-button" disabled={saving}>{editingScheme ? 'Save changes' : 'Create scheme'}</button>
                {editingScheme && <button className="secondary-button compact-button" type="button" onClick={() => { setEditingScheme(null); setSchemeForm(emptyScheme) }}>Cancel</button>}
              </div>
            </form>
            <article className="table-card">
              <h2>Academic schemes</h2>
              {schemes.length ? <table><thead><tr><th>Code</th><th>Name</th><th>Status</th><th /></tr></thead><tbody>
                {schemes.map((item) => <tr key={item.id}><td><strong>{item.code}</strong></td><td>{item.name}</td><td>{item.active ? 'Active' : 'Inactive'}</td><td className="table-actions"><button className="text-button" type="button" onClick={() => startEditScheme(item)}>Edit</button>{item.active && <button className="text-button danger-text" type="button" onClick={() => void confirmDeactivate('scheme', () => deleteWithAuth(`/admin/academic/schemes/${item.id}`, session))}>Deactivate</button>}</td></tr>)}
              </tbody></table> : <EmptyState title="No schemes" description="Create the first academic scheme." />}
            </article>
          </div>
        </div>
      )}

      {tab === 'semesters' && (
        <div role="tabpanel" id="panel-semesters" aria-labelledby="tab-semesters" tabIndex={0}>
          <div className="two-column-grid">
            <form className="editor-panel" onSubmit={submitSemester}>
              <h2>{editingSemester ? 'Edit semester' : 'New semester'}</h2>
              <label>Academic scheme<select value={semesterForm.academic_scheme_id} onChange={(event) => setSemesterForm({ ...semesterForm, academic_scheme_id: event.target.value })} required disabled={Boolean(editingSemester)}><option value="">Select scheme</option>{schemes.map((item) => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}</select></label>
              <label>Number<input type="number" min={1} max={8} value={semesterForm.number} onChange={(event) => setSemesterForm({ ...semesterForm, number: Number(event.target.value) })} required /></label>
              <label>Name<input value={semesterForm.name} onChange={(event) => setSemesterForm({ ...semesterForm, name: event.target.value })} required minLength={2} /></label>
              <div className="form-actions">
                <button className="primary-button compact-button" disabled={saving}>{editingSemester ? 'Save changes' : 'Create semester'}</button>
                {editingSemester && <button className="secondary-button compact-button" type="button" onClick={() => { setEditingSemester(null); setSemesterForm({ ...emptySemester, academic_scheme_id: semesterForm.academic_scheme_id }) }}>Cancel</button>}
              </div>
            </form>
            <article className="table-card">
              <h2>Semesters</h2>
              {semesters.length ? <table><thead><tr><th>Scheme</th><th>Number</th><th>Name</th><th>Status</th><th /></tr></thead><tbody>
                {semesters.map((item) => <tr key={item.id}><td>{schemes.find((scheme) => scheme.id === item.academic_scheme_id)?.code ?? '—'}</td><td>{item.number}</td><td>{item.name}</td><td>{item.active ? 'Active' : 'Inactive'}</td><td className="table-actions"><button className="text-button" type="button" onClick={() => startEditSemester(item)}>Edit</button>{item.active && <button className="text-button danger-text" type="button" onClick={() => void confirmDeactivate('semester', () => deleteWithAuth(`/admin/academic/semesters/${item.id}`, session))}>Deactivate</button>}</td></tr>)}
              </tbody></table> : <EmptyState title="No semesters" description="Create semesters for a scheme." />}
            </article>
          </div>
        </div>
      )}

      {tab === 'subjects' && (
        <div role="tabpanel" id="panel-subjects" aria-labelledby="tab-subjects" tabIndex={0}>
          <div className="two-column-grid">
            <form className="editor-panel" onSubmit={submitSubject}>
              <h2>{editingSubject ? 'Edit subject' : 'New subject'}</h2>
              <div className="editor-grid">
                <label>Academic scheme<select value={subjectForm.academic_scheme_id} onChange={(event) => setSubjectForm({ ...subjectForm, academic_scheme_id: event.target.value, semester_id: '', code: subjectForm.code })} required disabled={Boolean(editingSubject)}><option value="">Select scheme</option>{schemes.map((item) => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}</select></label>
                <label>Semester<select value={subjectForm.semester_id} onChange={(event) => setSubjectForm({ ...subjectForm, semester_id: event.target.value })} required><option value="">Select semester</option>{semesterOptions(subjectForm.academic_scheme_id).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                <label>Code<input value={subjectForm.code} onChange={(event) => setSubjectForm({ ...subjectForm, code: event.target.value })} required /></label>
                <label>Name<input value={subjectForm.name} onChange={(event) => setSubjectForm({ ...subjectForm, name: event.target.value })} required minLength={2} /></label>
                <label>Type<select value={subjectForm.subject_type} onChange={(event) => setSubjectForm({ ...subjectForm, subject_type: event.target.value })}><option value="CORE">Core</option><option value="ELECTIVE">Elective</option></select></label>
                <label>Credits<input type="number" min={0} max={30} value={subjectForm.credits} onChange={(event) => setSubjectForm({ ...subjectForm, credits: event.target.value })} placeholder="Optional" /></label>
              </div>
              <label>Description<textarea rows={3} value={subjectForm.description} onChange={(event) => setSubjectForm({ ...subjectForm, description: event.target.value })} /></label>
              <label className="checkbox-field"><input type="checkbox" checked={subjectForm.active} onChange={(event) => setSubjectForm({ ...subjectForm, active: event.target.checked })} /> Active</label>
              <div className="form-actions">
                <button className="primary-button compact-button" disabled={saving}>{editingSubject ? 'Save changes' : 'Create subject'}</button>
                {editingSubject && <button className="secondary-button compact-button" type="button" onClick={() => { setEditingSubject(null); setSubjectForm({ ...emptySubject, academic_scheme_id: subjectForm.academic_scheme_id, semester_id: semesterOptions(subjectForm.academic_scheme_id)[0]?.id ?? '' }) }}>Cancel</button>}
              </div>
            </form>
            <article className="table-card">
              <h2>Subjects</h2>
              {subjects.length ? <table><thead><tr><th>Code</th><th>Name</th><th>Type</th><th>Credits</th><th>Status</th><th /></tr></thead><tbody>
                {subjects.map((item) => <tr key={item.id}><td><strong>{item.code}</strong></td><td>{item.name}</td><td>{item.subject_type}</td><td>{item.credits ?? '—'}</td><td>{item.active ? 'Active' : 'Inactive'}</td><td className="table-actions"><button className="text-button" type="button" onClick={() => startEditSubject(item)}>Edit</button>{item.active && <button className="text-button danger-text" type="button" onClick={() => void confirmDeactivate('subject', () => deleteWithAuth(`/admin/academic/subjects/${item.id}`, session))}>Deactivate</button>}</td></tr>)}
              </tbody></table> : <EmptyState title="No subjects" description="Create subjects under a scheme and semester." />}
            </article>
          </div>
        </div>
      )}

      {tab === 'electives' && (
        <div role="tabpanel" id="panel-electives" aria-labelledby="tab-electives" tabIndex={0}>
          <div className="two-column-grid">
            <div>
              <form className="editor-panel" onSubmit={submitBasket}>
                <h2>New elective basket</h2>
                <label>Academic scheme<select value={basketForm.academic_scheme_id} onChange={(event) => setBasketForm({ ...basketForm, academic_scheme_id: event.target.value, semester_id: '' })} required><option value="">Select scheme</option>{schemes.map((item) => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}</select></label>
                <label>Semester<select value={basketForm.semester_id} onChange={(event) => setBasketForm({ ...basketForm, semester_id: event.target.value })} required><option value="">Select semester</option>{semesterOptions(basketForm.academic_scheme_id).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                <label>Basket name<input value={basketForm.name} onChange={(event) => setBasketForm({ ...basketForm, name: event.target.value })} required minLength={2} /></label>
                <div className="form-actions"><button className="primary-button compact-button" disabled={saving}>Create basket</button></div>
              </form>
              <form className="editor-panel" onSubmit={submitOption}>
                <h2>Add elective option</h2>
                <label>Basket<select value={optionForm.basket_id} onChange={(event) => setOptionForm({ basket_id: event.target.value, subject_id: '' })} required><option value="">Select basket</option>{baskets.filter((item) => item.active).map((item) => <option key={item.id} value={item.id}>{item.name} · {schemes.find((scheme) => scheme.id === item.academic_scheme_id)?.code ?? ''}</option>)}</select></label>
                <label>Elective subject<select value={optionForm.subject_id} onChange={(event) => setOptionForm({ ...optionForm, subject_id: event.target.value })} required disabled={!selectedOptionBasket}><option value="">Select elective subject</option>{selectedOptionBasket && electiveSubjects(selectedOptionBasket.academic_scheme_id, selectedOptionBasket.semester_id).map((item) => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}</select></label>
                <div className="form-actions"><button className="primary-button compact-button" disabled={saving || !selectedOptionBasket}>Add option</button></div>
              </form>
            </div>
            <article className="table-card">
              <h2>Elective baskets</h2>
              {baskets.length ? <table><thead><tr><th>Basket</th><th>Scheme</th><th>Semester</th><th>Options</th></tr></thead><tbody>
                {baskets.map((basket) => {
                  const options = electives.filter((item) => item.basket_id === basket.id)
                  return (
                    <tr key={basket.id}>
                      <td><strong>{basket.name}</strong>{!basket.active && <span className="table-subtext">Inactive</span>}</td>
                      <td>{schemes.find((scheme) => scheme.id === basket.academic_scheme_id)?.code ?? '—'}</td>
                      <td>{semesters.find((semester) => semester.id === basket.semester_id)?.name ?? '—'}</td>
                      <td>
                        {options.length ? options.map((option) => (
                          <span className="option-chip" key={option.subject_id}>
                            {option.subject_code}
                            <button className="chip-remove" type="button" aria-label={`Remove ${option.subject_code}`} onClick={() => void removeOption(option.basket_id, option.subject_id, option.subject_code)}>×</button>
                          </span>
                        )) : <span className="muted">No options</span>}
                      </td>
                    </tr>
                  )
                })}
               </tbody></table> : <EmptyState title="No elective baskets" description="Create a basket, then add elective subjects as options." />}
             </article>
           </div>
         </div>
       )}
    </section>
  )
}
