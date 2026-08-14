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
  screening_questions_available: boolean
  stage: PipelineStage
  messages: Message[]
  screening_transcript: string | null
  scheduled_at: string | null
  interview_notes: string | null
}

export interface UpcomingInterview {
  id: number
  candidate_name: string
  job_posting_title: string
  scheduled_at: string
}

export interface ScheduleInterviewRequest {
  scheduled_at: string
  interview_notes?: string | null
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

export type BusinessAccessStatus = 'unrequested' | 'pending_review' | 'active' | 'suspended'

export interface Business {
  id: number
  auth0_sub: string
  name: string
  owner_email: string | null
  needs_onboarding: boolean
  status: BusinessAccessStatus
  created_at: string
}

export interface BusinessUpdate {
  name: string
}

export interface RequestAccessResult {
  status: BusinessAccessStatus
  message: string
}

export interface AdminBusiness {
  id: number
  name: string
  auth0_sub: string
  requested_by_email: string | null
  owner_email: string | null
  status: BusinessAccessStatus
  created_at: string
  job_posting_count: number
}

export type McpServerState = 'starting' | 'running' | 'error' | 'disconnected'

export interface McpStatus {
  status: McpServerState
  channels: Record<string, string>
}

export interface JsonSchemaProperty {
  type?: string
  description?: string
  default?: unknown
  enum?: (string | number)[]
}

export interface McpToolInputSchema {
  type?: string
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
}

export interface McpTool {
  name: string
  description: string | null
  input_schema: McpToolInputSchema
}

export interface McpToolCallResult {
  is_error: boolean
  content: string[]
  structured_content: unknown
}

export interface JobPostingSummary {
  id: number
  title: string
  location: string
  employment_type: string
  is_active: boolean
  faq_count: number
  screening_question_count: number
}

export interface FaqEntry {
  question: string
  answer: string
}

export interface JobPostingDetail {
  id: number
  title: string
  description: string
  location: string
  employment_type: string
  is_active: boolean
  faq: FaqEntry[]
  screening_questions: string[]
}

export interface JobPostingConfigUpdate {
  faq: FaqEntry[]
  screening_questions: string[]
}
