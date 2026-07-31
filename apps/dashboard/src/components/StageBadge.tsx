import { Badge } from '@/components/ui/badge'
import type { PipelineStage } from '@/lib/types'

const STAGE_LABELS: Record<PipelineStage, string> = {
  applied: 'Applied',
  screening_assigned: 'Screening Assigned',
  screening_completed: 'Screening Completed',
  shortlisted: 'Shortlisted',
  interview_scheduled: 'Interview Scheduled',
  confirmed: 'Confirmed',
}

export function StageBadge({ stage }: { stage: PipelineStage }) {
  return <Badge variant="secondary">{STAGE_LABELS[stage]}</Badge>
}
