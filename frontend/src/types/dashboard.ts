export interface SubjectSummary {
  id: string
  code: string
  name: string
  subject_type: string
  credits: number | null
  semester: string | null
  semester_number: number | null
  syllabus_available: boolean
  pyq_count: number
  pyq_available: boolean
  learning_resources_available: boolean
  learning_resource_count: number
}

export interface StudentDashboardData {
  welcome_name: string
  profile: {
    usn: string | null
    department: string | null
    branch: string | null
    academic_scheme: string | null
    semester: string | null
    semester_number: number | null
    selected_elective: string | null
    enrollment_year: number | null
    onboarding_completed: boolean
  }
  academic_overview: {
    current_semester: string | null
    enrolled_subjects: number
    subjects_with_syllabus: number
    subjects_with_pyqs: number
    subjects_with_resources: number
    learning_resources_available: boolean
    learning_resource_count: number
    pyq_count: number
  }
  subjects: SubjectSummary[]
  enrolled_subjects: { id: string; code: string; name: string }[]
  academic_preparation: { status: string; progress_available: boolean }
  progress: { started_topics: number; completed_topics: number; bookmarked_topics: number }
  recent_activity: unknown[]
}

export interface StudentProfileData {
  id: string
  student_name: string
  email: string
  usn: string | null
  branch_id: string | null
  branch: string | null
  academic_scheme_id: string | null
  academic_scheme: string | null
  current_semester_id: string | null
  semester: string | null
  selected_elective_id: string | null
  selected_elective: string | null
  enrollment_year: number | null
  profile_completed: boolean
}

export interface ContentItem {
  id: string
  subject_id: string
  subject_code: string | null
  subject_name: string | null
  original_filename: string
  file_type: string
  file_size?: number | null
  title?: string | null
  description?: string | null
  verification_status: string
  active?: boolean
}

export interface SyllabusDocumentItem extends ContentItem {
  version?: string
  version_id?: string
  title?: string
  created_at?: string | null
}

export interface QuestionPaperItem extends ContentItem {
  document_id?: string
  title?: string
  description?: string | null
  exam_type: string
  cie_number: number | null
  examination_year: number | null
  uploaded_at?: string | null
}

export interface LearningResourceItem extends ContentItem {
  title: string
  description: string | null
  resource_type: string
  uploaded_at?: string | null
}

export interface StudentSubjectDetail {
  subject: {
    id: string
    code: string
    name: string
    subject_type: string
    credits: number | null
    description: string | null
    semester: string | null
    semester_number: number | null
    academic_scheme: string | null
  }
  syllabus: SyllabusDocumentItem[]
  pyqs: QuestionPaperItem[]
  resources: LearningResourceItem[]
}

export interface AdminActivityItem {
  type: string
  title: string
  detail: string | null
  at: string | null
}

export interface AdminDashboardData {
  welcome_name: string
  profile: { email: string; role: string }
  catalog_overview: {
    subjects: number
    semesters: number
    branches: number
    academic_schemes: number
  }
  user_overview: { students: number; administrators: number }
  document_overview: {
    uploaded_documents: number
    pyqs: number
    syllabus_documents: number
    learning_resources: number
    pending_reviews: number
  }
  recent_activity: AdminActivityItem[]
  document_management_available: boolean
}

export interface AdminUserItem {
  id: string
  full_name: string
  email: string
  role: string
  account_status: string
  email_verified: boolean
  created_at: string | null
  last_login_at: string | null
  student_profile: {
    usn: string | null
    profile_completed: boolean
    branch_id: string | null
    current_semester_id: string | null
    branch_name?: string | null
    semester_name?: string | null
  } | null
}

export interface PaginatedUsers {
  items: AdminUserItem[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface AcademicCatalog {
  branches: { id: string; name: string; code: string; active: boolean; college_id?: string }[]
  schemes: { id: string; name: string; code: string; active: boolean; college_id?: string }[]
  semesters: {
    id: string
    number: number
    name: string
    active: boolean
    academic_scheme_id?: string
  }[]
  subjects: {
    id: string
    code: string
    name: string
    subject_type: string
    credits: number | null
    description?: string | null
    semester_id: string
    academic_scheme_id: string
    active: boolean
  }[]
  electives: {
    basket_id: string
    basket_name: string
    subject_id: string
    subject_code: string
    subject_name: string
    active: boolean
  }[]
}
