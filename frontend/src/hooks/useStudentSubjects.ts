import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { getWithAuth } from '../services/authApi'
import type { SubjectSummary } from '../types/dashboard'

export function useStudentSubjects() {
  const { session } = useAuth()
  const [subjects, setSubjects] = useState<SubjectSummary[]>([])

  useEffect(() => {
    let active = true
    getWithAuth<{ subjects: SubjectSummary[] }>('/auth/student/subjects', session)
      .then((data) => {
        if (active) setSubjects(data.subjects)
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
