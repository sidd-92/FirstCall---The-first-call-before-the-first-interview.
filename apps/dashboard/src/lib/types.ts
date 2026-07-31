export type PipelineStage =
  | 'applied'
  | 'screening_assigned'
  | 'screening_completed'
  | 'shortlisted'
  | 'interview_scheduled'
  | 'confirmed'

export interface CandidateSummary {
  id: number
  name: string
  job_posting_title: string
  stage: PipelineStage
  last_activity_at: string
}

export interface Message {
  id: number
  direction: 'inbound' | 'outbound'
  content: string
  created_at: string
}

export interface CandidateDetail {
  id: number
  name: string
  email: string
  phone: string
  address: string
  resume_file_path: string
  job_posting_title: string
  stage: PipelineStage
  messages: Message[]
  screening_transcript: string | null
}

export interface UpcomingInterview {
  id: number
  candidate_name: string
  job_posting_title: string
  scheduled_at: string
}

export interface JobPostingCreate {
  title: string
  description: string
  location: string
  employment_type: string
  pay_min: number | null
  pay_max: number | null
  pay_currency: string
  benefits: string[]
}

export interface Business {
  id: number
  auth0_sub: string
  name: string
  owner_email: string | null
  created_at: string
}

export interface BusinessOnboard {
  name: string
  owner_email: string | null
}
