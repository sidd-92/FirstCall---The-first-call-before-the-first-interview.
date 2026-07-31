import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useAuthedApi } from '@/lib/useAuthedApi'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

export function PostJobPage() {
  const { createJobPosting } = useAuthedApi()
  const navigate = useNavigate()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const form = event.currentTarget
    const formData = new FormData(form)
    const payMin = formData.get('pay_min')
    const payMax = formData.get('pay_max')
    const benefits = String(formData.get('benefits') ?? '')
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)

    setSubmitting(true)
    setError(null)
    try {
      const { id } = await createJobPosting({
        title: String(formData.get('title') ?? ''),
        description: String(formData.get('description') ?? ''),
        location: String(formData.get('location') ?? ''),
        employment_type: String(formData.get('employment_type') ?? ''),
        pay_min: payMin ? Number(payMin) : null,
        pay_max: payMax ? Number(payMax) : null,
        pay_currency: String(formData.get('pay_currency') ?? 'INR'),
        benefits,
      })
      navigate(`/`, { state: { newJobPostingId: id } })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create job posting.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-6 text-2xl font-semibold tracking-tight">Post a job</h1>

      <Card>
        <CardHeader>
          <CardTitle>Job details</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="title">Job title</Label>
              <Input id="title" name="title" required />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="location">Location</Label>
              <Input id="location" name="location" placeholder="Hyderabad, Telangana" required />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="employment_type">Job type</Label>
              <Input
                id="employment_type"
                name="employment_type"
                placeholder="Permanent, Full-time"
                required
              />
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pay_min">Pay (min)</Label>
                <Input id="pay_min" name="pay_min" type="number" min={0} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pay_max">Pay (max)</Label>
                <Input id="pay_max" name="pay_max" type="number" min={0} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pay_currency">Currency</Label>
                <Input id="pay_currency" name="pay_currency" defaultValue="INR" required />
              </div>
            </div>
            <p className="-mt-2 text-xs text-muted-foreground">Pay is per year.</p>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="benefits">Benefits</Label>
              <Textarea
                id="benefits"
                name="benefits"
                placeholder={'One per line, e.g.\nPaid time off\nProvident Fund'}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="description">Full job description</Label>
              <Textarea id="description" name="description" className="min-h-40" required />
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <Button type="submit" disabled={submitting}>
              {submitting ? 'Posting...' : 'Post job'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
