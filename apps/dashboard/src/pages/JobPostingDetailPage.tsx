import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router'
import { useAuthedApi } from '@/lib/useAuthedApi'
import type { FaqEntry, JobPostingDetail } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

export function JobPostingDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { getJobPosting, updateJobPostingConfig } = useAuthedApi()
  const [posting, setPosting] = useState<JobPostingDetail | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [faq, setFaq] = useState<FaqEntry[]>([])
  const [screeningQuestionsText, setScreeningQuestionsText] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!id) return
    getJobPosting(id)
      .then((detail) => {
        setPosting(detail)
        setFaq(detail.faq)
        setScreeningQuestionsText(detail.screening_questions.join('\n'))
      })
      .catch((err: Error) => setLoadError(err.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  function updateFaqField(index: number, field: keyof FaqEntry) {
    return (event: React.ChangeEvent<HTMLInputElement>) => {
      setFaq((prev) =>
        prev.map((entry, i) => (i === index ? { ...entry, [field]: event.target.value } : entry)),
      )
    }
  }

  function removeFaqEntry(index: number) {
    setFaq((prev) => prev.filter((_, i) => i !== index))
  }

  function addFaqEntry() {
    setFaq((prev) => [...prev, { question: '', answer: '' }])
  }

  async function handleSave() {
    if (!id) return
    setSaving(true)
    setSaveError(null)
    setSaved(false)
    try {
      const screening_questions = screeningQuestionsText
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
      const cleanedFaq = faq
        .map((entry) => ({ question: entry.question.trim(), answer: entry.answer.trim() }))
        .filter((entry) => entry.question && entry.answer)

      await updateJobPostingConfig(id, { faq: cleanedFaq, screening_questions })
      setFaq(cleanedFaq)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save.')
    } finally {
      setSaving(false)
    }
  }

  if (loadError) {
    return (
      <div>
        <p className="text-destructive">Failed to load job posting: {loadError}</p>
        <Link to="/jobs" className="text-sm text-primary underline-offset-4 hover:underline">
          &larr; Back to job postings
        </Link>
      </div>
    )
  }

  if (!posting) {
    return <p className="text-muted-foreground">Loading...</p>
  }

  return (
    <div className="mx-auto max-w-2xl">
      <Link to="/jobs" className="text-sm text-muted-foreground hover:text-foreground">
        &larr; Back to job postings
      </Link>

      <h1 className="mt-4 mb-6 text-2xl font-semibold tracking-tight">{posting.title}</h1>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Screening questions</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <p className="text-sm text-muted-foreground">
            One per line. Asked in this fixed order over Discord once a candidate is assigned
            screening -- Agent 1 reads this live, so saving takes effect on the candidate&apos;s
            very next message.
          </p>
          <Label htmlFor="screening-questions">Questions</Label>
          <Textarea
            id="screening-questions"
            className="min-h-32"
            placeholder={'Tell me about your relevant experience.\nWhat are your salary expectations?'}
            value={screeningQuestionsText}
            onChange={(event) => setScreeningQuestionsText(event.target.value)}
          />
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>FAQ</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="-mt-2 text-sm text-muted-foreground">
            Answered automatically over email; falls back to an LLM for questions not covered
            here.
          </p>
          {faq.map((entry, index) => (
            <div key={index} className="flex flex-col gap-2 rounded-md border p-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`faq-question-${index}`}>Question</Label>
                <Input
                  id={`faq-question-${index}`}
                  value={entry.question}
                  onChange={updateFaqField(index, 'question')}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`faq-answer-${index}`}>Answer</Label>
                <Input
                  id={`faq-answer-${index}`}
                  value={entry.answer}
                  onChange={updateFaqField(index, 'answer')}
                />
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="w-fit text-destructive"
                onClick={() => removeFaqEntry(index)}
              >
                Remove
              </Button>
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" className="w-fit" onClick={addFaqEntry}>
            + Add FAQ entry
          </Button>
        </CardContent>
      </Card>

      {saveError && <p className="mb-3 text-sm text-destructive">{saveError}</p>}

      <Button onClick={handleSave} disabled={saving}>
        {saving ? 'Saving...' : saved ? 'Saved!' : 'Save changes'}
      </Button>
    </div>
  )
}
