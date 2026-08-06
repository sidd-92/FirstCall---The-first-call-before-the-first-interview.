import { useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Outlet } from 'react-router'
import { useAuthedApi } from '@/lib/useAuthedApi'
import type { Business } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

/**
 * Gates every protected route behind first-time onboarding. The backend
 * auto-creates a placeholder Business row the moment a new Auth0 account
 * makes its first authenticated request (see get_current_actor_and_business
 * in services/backend/src/auth.py) -- there is no admin step. This
 * component just detects that placeholder (`needs_onboarding`) via
 * GET /business/me and asks for a real business name via PATCH /business/me
 * before letting the user reach the normal dashboard routes.
 */
export function OnboardingGate() {
  const { isAuthenticated } = useAuth0()
  const { getMyBusiness, updateMyBusiness } = useAuthedApi()
  const [business, setBusiness] = useState<Business | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    if (!isAuthenticated) return
    getMyBusiness()
      .then(setBusiness)
      .catch((err: Error) => setLoadError(err.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated])

  if (!isAuthenticated) return <Outlet />

  if (loadError) {
    return (
      <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-destructive">
        <p className="font-medium">Failed to load your business profile</p>
        <p className="text-sm">{loadError}</p>
      </div>
    )
  }

  if (business === null) {
    return <p className="text-muted-foreground">Loading...</p>
  }

  if (!business.needs_onboarding) {
    return <Outlet />
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const name = String(new FormData(event.currentTarget).get('name') ?? '').trim()
    if (!name) return

    setSubmitting(true)
    setSubmitError(null)
    try {
      setBusiness(await updateMyBusiness({ name }))
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to save business name.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <Card>
        <CardHeader>
          <CardTitle>Welcome to FirstCall</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-4 text-sm text-muted-foreground">
            What&apos;s your business name?
          </p>
          <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="name">Business name</Label>
              <Input id="name" name="name" required autoFocus />
            </div>
            {submitError && <p className="text-sm text-destructive">{submitError}</p>}
            <Button type="submit" disabled={submitting} className="w-fit">
              {submitting ? 'Saving...' : 'Continue'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
