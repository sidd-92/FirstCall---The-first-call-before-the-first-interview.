import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useAuthedApi } from '@/lib/useAuthedApi'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

interface JobFormState {
  title: string
  location: string
  employment_type: string
  pay_min: string
  pay_max: string
  pay_currency: string
  benefits: string
  description: string
}

const JSON_FIELDS = [
  'title',
  'description',
  'location',
  'employment_type',
  'pay_min',
  'pay_max',
  'pay_currency',
  'benefits',
] as const

const EMPTY_FORM: JobFormState = {
  title: '',
  location: '',
  employment_type: '',
  pay_min: '',
  pay_max: '',
  pay_currency: 'INR',
  benefits: '',
  description: '',
}

export function PostJobPage() {
  const { createJobPosting } = useAuthedApi()
  const navigate = useNavigate()
  const [form, setForm] = useState<JobFormState>(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showJson, setShowJson] = useState(false)
  const [jsonDraft, setJsonDraft] = useState('')
  const [jsonError, setJsonError] = useState<string | null>(null)

  function updateField(field: keyof JobFormState) {
    return (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setForm((prev) => ({ ...prev, [field]: event.target.value }))
    }
  }

  function handleJsonAdd() {
    setJsonError(null)

    let parsed: unknown
    try {
      parsed = JSON.parse(jsonDraft)
    } catch {
      setJsonError('Invalid JSON.')
      return
    }

    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      setJsonError('Expected a JSON object.')
      return
    }

    const record = parsed as Record<string, unknown>
    const next: JobFormState = { ...form }

    for (const key of JSON_FIELDS) {
      const value = record[key]
      if (value === undefined) continue

      if (key === 'benefits') {
        if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) {
          setJsonError('benefits must be an array of strings.')
          return
        }
        next.benefits = (value as string[]).join('\n')
      } else if (key === 'pay_min' || key === 'pay_max') {
        if (typeof value !== 'number' && typeof value !== 'string') {
          setJsonError(`${key} must be a number.`)
          return
        }
        next[key] = String(value)
      } else if (typeof value === 'string') {
        next[key] = value
      } else {
        setJsonError(`${key} must be a string.`)
        return
      }
    }

    setForm(next)
    setJsonDraft('')
    setShowJson(false)
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const payMin = form.pay_min ? Number(form.pay_min) : null
    const payMax = form.pay_max ? Number(form.pay_max) : null
    const benefits = form.benefits
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)

    setSubmitting(true)
    setError(null)
    try {
      const { id } = await createJobPosting({
        title: form.title,
        description: form.description,
        location: form.location,
        employment_type: form.employment_type,
        pay_min: payMin,
        pay_max: payMax,
        pay_currency: form.pay_currency,
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
          <div className="flex items-center justify-between">
            <CardTitle>Job details</CardTitle>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowJson((value) => !value)}
            >
              Load from JSON
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {showJson && (
            <div className="mb-6 flex flex-col gap-3 rounded-md border p-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="json">Job JSON</Label>
                <Textarea
                  id="json"
                  value={jsonDraft}
                  onChange={(event) => setJsonDraft(event.target.value)}
                  placeholder={'{\n  "title": "Senior Software Engineer",\n  "location": "Bengaluru, India"\n}'}
                  className="min-h-40 font-mono text-xs"
                />
              </div>
              {jsonError && <p className="text-sm text-destructive">{jsonError}</p>}
              <div className="flex gap-2">
                <Button type="button" size="sm" onClick={handleJsonAdd}>
                  Add to form
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setJsonDraft('')
                    setJsonError(null)
                    setShowJson(false)
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}

          <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="title">Job title</Label>
              <Input
                id="title"
                name="title"
                value={form.title}
                onChange={updateField('title')}
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="location">Location</Label>
              <Input
                id="location"
                name="location"
                placeholder="Hyderabad, Telangana"
                value={form.location}
                onChange={updateField('location')}
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="employment_type">Job type</Label>
              <Input
                id="employment_type"
                name="employment_type"
                placeholder="Permanent, Full-time"
                value={form.employment_type}
                onChange={updateField('employment_type')}
                required
              />
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pay_min">Pay (min)</Label>
                <Input
                  id="pay_min"
                  name="pay_min"
                  type="number"
                  min={0}
                  value={form.pay_min}
                  onChange={updateField('pay_min')}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pay_max">Pay (max)</Label>
                <Input
                  id="pay_max"
                  name="pay_max"
                  type="number"
                  min={0}
                  value={form.pay_max}
                  onChange={updateField('pay_max')}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pay_currency">Currency</Label>
                <Input
                  id="pay_currency"
                  name="pay_currency"
                  value={form.pay_currency}
                  onChange={updateField('pay_currency')}
                  required
                />
              </div>
            </div>
            <p className="-mt-2 text-xs text-muted-foreground">Pay is per year.</p>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="benefits">Benefits</Label>
              <Textarea
                id="benefits"
                name="benefits"
                placeholder={'One per line, e.g.\nPaid time off\nProvident Fund'}
                value={form.benefits}
                onChange={updateField('benefits')}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="description">Full job description</Label>
              <Textarea
                id="description"
                name="description"
                className="min-h-40"
                value={form.description}
                onChange={updateField('description')}
                required
              />
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
