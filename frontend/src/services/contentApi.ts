import { getWithAuth, patchWithAuth, deleteWithAuth, uploadWithAuth, authHeaders } from './authApi'
import api from './api'
import type {
  LearningResourceItem,
  QuestionPaperItem,
  StudentSubjectDetail,
  SyllabusDocumentItem,
} from '../types/dashboard'
import type { AuthSession } from '../types/auth'

export type ContentKind = 'syllabus' | 'pyq' | 'resource'

function query(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value))
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

export interface ContentListResult<T> {
  items: T[]
  total: number
}

export function listStudentSyllabus(
  session: AuthSession | null,
  params: { search?: string; subject_id?: string } = {},
) {
  return getWithAuth<ContentListResult<SyllabusDocumentItem>>(
    `/student/syllabus${query(params)}`,
    session,
  )
}

export function listStudentPyqs(
  session: AuthSession | null,
  params: { search?: string; subject_id?: string; year?: number; exam_type?: string } = {},
) {
  return getWithAuth<ContentListResult<QuestionPaperItem>>(`/student/pyqs${query(params)}`, session)
}

export function listStudentResources(
  session: AuthSession | null,
  params: { search?: string; subject_id?: string; resource_type?: string } = {},
) {
  return getWithAuth<ContentListResult<LearningResourceItem>>(
    `/student/resources${query(params)}`,
    session,
  )
}

export function getStudentSubject(session: AuthSession | null, subjectId: string) {
  return getWithAuth<StudentSubjectDetail>(`/student/subjects/${subjectId}`, session)
}

async function signedContentUrl(
  session: AuthSession | null,
  path: string,
  preview: boolean,
): Promise<string> {
  const response = await api.get<{ url: string; filename?: string; disposition?: string }>(path, {
    headers: authHeaders(session),
    params: preview ? { preview: 'true' } : undefined,
  })
  return response.data.url
}

export async function openStudentDownload(
  session: AuthSession | null,
  kind: ContentKind,
  id: string,
): Promise<string> {
  return signedContentUrl(session, `/student/${kind}/${id}/download`, false)
}

export async function openStudentPreview(
  session: AuthSession | null,
  kind: ContentKind,
  id: string,
): Promise<string> {
  return signedContentUrl(session, `/student/${kind}/${id}/download`, true)
}

export interface AdminUploadPayload {
  subject_id: string
  status: string
  file?: File | null
  resource_source?: 'FILE' | 'LINK' | 'BOTH'
  external_url?: string
  link_title?: string
  unit_id?: string
  version?: string
  title?: string
  description?: string
  exam_type?: string
  examination_year?: number
  cie_number?: number
  resource_type?: string
}

export async function uploadAdminContent(
  session: AuthSession | null,
  kind: ContentKind,
  payload: AdminUploadPayload,
) {
  const form = new FormData()
  if (payload.file) form.set('file', payload.file)
  form.set('subject_id', payload.subject_id)
  form.set('status', payload.status)
  if (payload.resource_source) form.set('resource_source', payload.resource_source)
  if (payload.external_url) form.set('external_url', payload.external_url)
  if (payload.link_title) form.set('link_title', payload.link_title)
  if (payload.unit_id) form.set('unit_id', payload.unit_id)
  if (payload.version) form.set('version', payload.version)
  if (payload.title) form.set('title', payload.title)
  if (payload.description) form.set('description', payload.description)
  if (payload.exam_type) form.set('exam_type', payload.exam_type)
  if (payload.examination_year) form.set('examination_year', String(payload.examination_year))
  if (payload.cie_number) form.set('cie_number', String(payload.cie_number))
  if (payload.resource_type) form.set('resource_type', payload.resource_type)
  const endpoint = kind === 'pyq' ? 'pyqs' : kind === 'syllabus' ? 'syllabus' : 'resources'
  return uploadWithAuth<Record<string, unknown>>(`/admin/${endpoint}`, session, form)
}

export interface AdminUnitItem {
  id: string
  title: string
  order_index: number
}

export async function listAdminUnits(
  session: AuthSession | null,
  subjectId: string,
): Promise<AdminUnitItem[]> {
  return getWithAuth<AdminUnitItem[]>(`/admin/subjects/${subjectId}/units`, session)
}

export async function listAdminContent<T = unknown>(
  session: AuthSession | null,
  kind: ContentKind,
  params = '',
) {
  const endpoint = kind === 'pyq' ? 'pyqs' : kind === 'syllabus' ? 'syllabus' : 'resources'
  return getWithAuth<ContentListResult<T>>(`/admin/${endpoint}${params}`, session)
}

export async function updateAdminContent(
  session: AuthSession | null,
  kind: ContentKind,
  id: string,
  body: Record<string, unknown>,
) {
  const endpoint = kind === 'pyq' ? 'pyqs' : kind === 'syllabus' ? 'syllabus' : 'resources'
  return patchWithAuth<Record<string, unknown>>(`/admin/${endpoint}/${id}`, session, body)
}

export async function archiveAdminContent(
  session: AuthSession | null,
  kind: ContentKind,
  id: string,
) {
  const endpoint = kind === 'pyq' ? 'pyqs' : kind === 'syllabus' ? 'syllabus' : 'resources'
  return deleteWithAuth<{ message: string }>(`/admin/${endpoint}/${id}`, session)
}

export async function deleteAdminContent(
  session: AuthSession | null,
  kind: ContentKind | 'document',
  id: string,
) {
  const endpoint = kind === 'pyq' ? 'pyqs' : kind === 'syllabus' ? 'syllabus' : kind === 'resource' ? 'resources' : 'documents'
  return deleteWithAuth<{ message: string }>(`/admin/${endpoint}/${id}?permanent=true`, session)
}

export async function openAdminDownload(
  session: AuthSession | null,
  kind: ContentKind,
  id: string,
): Promise<string> {
  return signedContentUrl(session, `/admin/${kind}/${id}/download`, false)
}

export async function openAdminPreview(
  session: AuthSession | null,
  kind: ContentKind,
  id: string,
): Promise<string> {
  return signedContentUrl(session, `/admin/${kind}/${id}/download`, true)
}
