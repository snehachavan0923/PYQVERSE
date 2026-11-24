import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { getWithAuth } from '../services/authApi'

export interface AdminSubjectOption {
  id: string
  code: string
  name: string
  subject_type: string
  semester_id: string
  academic_scheme_id: string
  active: boolean
}

export function useAdminSubjects() {
  const { session } = useAuth()
  const [subjects, setSubjects] = useState<AdminSubjectOption[]>([])

  useEffect(() => {
    let active = true
    getWithAuth<AdminSubjectOption[]>('/admin/academic/subjects', session)
      .then((data) => {
        if (active) setSubjects(data)
      })
      .catch(() => {
        if (active) setSubjects([])
      })
    return () => {
      active = false
    }
  }, [session])

  return subjects
}
