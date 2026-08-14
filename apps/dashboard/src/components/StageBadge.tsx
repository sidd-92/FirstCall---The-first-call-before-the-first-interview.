import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { PipelineStage } from '@/lib/types'

const STAGE_LABELS: Record<PipelineStage, string> = {
  applied: 'Applied',
  screening_assigned: 'Screening Assigned',
  screening_completed: 'Screening Completed',
  shortlisted: 'Shortlisted',
  interview_scheduled: 'Interview Scheduled',
  confirmed: 'Confirmed',
}

// Stages the candidate is actively waiting on get the accent-outline
// treatment; earlier/later stages stay neutral so the active step reads at
// a glance in the pipeline table.
const ACTIVE_STAGES: PipelineStage[] = ['screening_assigned', 'screening_completed', 'interview_scheduled']

export function StageBadge({ stage }: { stage: PipelineStage }) {
  const isActive = ACTIVE_STAGES.includes(stage)
  return (
    <Badge
      variant="outline"
      className={cn(isActive && 'border-accent text-accent')}
    >
      {STAGE_LABELS[stage]}
    </Badge>
  )
}
