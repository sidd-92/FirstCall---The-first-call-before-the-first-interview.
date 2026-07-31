import { useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { useAuthedApi } from '@/lib/useAuthedApi'
import type { Business } from '@/lib/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export function BusinessesPage() {
  const { user } = useAuth0()
  const { listBusinesses, onboardBusiness } = useAuthedApi()
  const [businesses, setBusinesses] = useState<Business[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [onboarding, setOnboarding] = useState(false)
  const [onboardingError, setOnboardingError] = useState<string | null>(null)

  const refresh = () => {
    listBusinesses()
      .then(setBusinesses)
      .catch((err: Error) => setError(err.message))
  }

  useEffect(refresh, []) // eslint-disable-line react-hooks/exhaustive-deps

  const currentUserSub = user?.sub
  const isRegistered = businesses?.some((b) => b.auth0_sub === currentUserSub) ?? false

  async function handleOnboard(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const formData = new FormData(form)
    setOnboarding(true)
    setOnboardingError(null)
    try {
      await onboardBusiness({
        name: String(formData.get('name') ?? ''),
        owner_email: String(formData.get('owner_email') ?? '') || null,
      })
      refresh()
    } catch (err) {
      setOnboardingError(err instanceof Error ? err.message : 'Failed to register business.')
    } finally {
      setOnboarding(false)
    }
  }

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight">Businesses</h1>

      {error && <p className="mb-4 text-destructive">Failed to load businesses: {error}</p>}
      {!error && businesses === null && (
        <p className="text-muted-foreground">Loading...</p>
      )}

      {businesses !== null && !isRegistered && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Register your business</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-4 text-sm text-muted-foreground">
              Your account isn&apos;t linked to a business yet. Register one to start posting
              jobs.
            </p>
            <form className="flex flex-col gap-4" onSubmit={handleOnboard}>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="name">Business name</Label>
                <Input id="name" name="name" required />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="owner_email">Owner email</Label>
                <Input id="owner_email" name="owner_email" type="email" />
              </div>
              {onboardingError && <p className="text-sm text-destructive">{onboardingError}</p>}
              <Button type="submit" disabled={onboarding} className="w-fit">
                {onboarding ? 'Registering...' : 'Register business'}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {businesses?.length === 0 && (
        <p className="text-muted-foreground">No businesses registered yet.</p>
      )}

      {businesses && businesses.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>All businesses</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Auth0 sub</TableHead>
                  <TableHead>Owner email</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {businesses.map((business) => (
                  <TableRow key={business.id}>
                    <TableCell>{business.id}</TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-2 font-medium">
                        {business.name}
                        {business.auth0_sub === currentUserSub && <Badge>You</Badge>}
                      </span>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{business.auth0_sub}</TableCell>
                    <TableCell>{business.owner_email ?? '—'}</TableCell>
                    <TableCell>{new Date(business.created_at).toLocaleDateString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
