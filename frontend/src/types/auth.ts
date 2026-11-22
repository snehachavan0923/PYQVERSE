export type UserRole = 'STUDENT' | 'ADMIN_FACULTY'

export interface AuthProfile {
  id: string
  role: UserRole
  onboarding_completed: boolean
}

export interface AuthSession {
  access_token: string
  refresh_token: string
  user: {
    id: string
    email: string
    email_verified: boolean
  }
  profile: AuthProfile
}
