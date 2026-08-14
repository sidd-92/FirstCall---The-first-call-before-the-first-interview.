import { useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { useAuthedApi } from '@/lib/useAuthedApi'
import type { AdminBusiness } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

// Only used to decide whether to render this page's content at all -- real
// enforcement is server-side (services/backend/src/auth.py's require_admin,
// checked against the same PLATFORM_ADMIN_EMAIL). This just keeps a non-admin
// from seeing a page that would 403 on every request anyway.
const PLATFORM_ADMIN_EMAIL = import.meta.env.VITE_PLATFORM_ADMIN_EMAIL as string | undefined

const STATUS_LABELS: Record<AdminBusiness['status'], string> = {
  unrequested: 'Unrequested',
  pending_review: 'Pending review',
  active: 'Active',
  suspended: 'Suspended',
}

export function AdminPage() {
  const { user } = useAuth0()
  const { adminListBusinesses, adminApproveBusiness } = useAuthedApi()
  const [businesses, setBusinesses] = useState<AdminBusiness[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [approvingId, setApprovingId] = useState<number | null>(null)
  const [allBusinesses, setAllBusinesses] = useState<AdminBusiness[] | null>(null)
  const [allError, setAllError] = useState<string | null>(null)

  const isAdmin = Boolean(PLATFORM_ADMIN_EMAIL) && user?.email === PLATFORM_ADMIN_EMAIL

  function refresh() {
    adminListBusinesses('pending_review')
      .then(setBusinesses)
      .catch((err: Error) => setError(err.message))
    adminListBusinesses()
      .then(setAllBusinesses)
      .catch((err: Error) => setAllError(err.message))
  }

  useEffect(() => {
    if (isAdmin) refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin])

  if (!isAdmin) {
    return <p className="text-muted-foreground">You don&apos;t have access to this page.</p>
  }

  async function handleApprove(id: number) {
    setApprovingId(id)
    setError(null)
    try {
      await adminApproveBusiness(id)
      refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to approve business.')
    } finally {
      setApprovingId(null)
    }
  }

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight">Pending access requests</h1>

      {error && <p className="mb-4 text-destructive">{error}</p>}
      {!error && businesses === null && <p className="text-muted-foreground">Loading...</p>}
      {businesses?.length === 0 && <p className="text-muted-foreground">No pending requests.</p>}

      {businesses && businesses.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Awaiting review</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Requested by</TableHead>
                  <TableHead>Auth0 sub</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {businesses.map((business) => (
                  <TableRow key={business.id}>
                    <TableCell className="font-medium">{business.name}</TableCell>
                    <TableCell>{business.requested_by_email ?? '—'}</TableCell>
                    <TableCell className="font-mono text-xs">{business.auth0_sub}</TableCell>
                    <TableCell>{new Date(business.created_at).toLocaleDateString()}</TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        disabled={approvingId === business.id}
                        onClick={() => handleApprove(business.id)}
                      >
                        {approvingId === business.id ? 'Approving...' : 'Approve'}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <h2 className="mt-10 mb-6 text-2xl font-semibold tracking-tight">All businesses</h2>

      {allError && <p className="mb-4 text-destructive">{allError}</p>}
      {!allError && allBusinesses === null && <p className="text-muted-foreground">Loading...</p>}
      {allBusinesses?.length === 0 && <p className="text-muted-foreground">No businesses yet.</p>}

      {allBusinesses && allBusinesses.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Businesses ({allBusinesses.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Owner</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Jobs posted</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {allBusinesses.map((business) => (
                  <TableRow key={business.id}>
                    <TableCell className="font-medium">{business.name}</TableCell>
                    <TableCell>{business.owner_email ?? business.requested_by_email ?? '—'}</TableCell>
                    <TableCell>{STATUS_LABELS[business.status]}</TableCell>
                    <TableCell>{business.job_posting_count}</TableCell>
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
