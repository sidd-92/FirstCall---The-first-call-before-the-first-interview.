import { useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Link, useLocation } from 'react-router'
import { useAuthedApi } from '@/lib/useAuthedApi'
import type { Business } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { OnboardingGate } from '@/components/OnboardingGate'
import { cn } from '@/lib/utils'

// Must match the backend's PLATFORM_ADMIN_EMAIL -- see apps/dashboard/.env.example.
const PLATFORM_ADMIN_EMAIL = import.meta.env.VITE_PLATFORM_ADMIN_EMAIL as string | undefined

const BASE_NAV_LINKS = [
  { to: '/', label: 'Candidates' },
  { to: '/interviews', label: 'Interviews' },
  { to: '/jobs', label: 'Jobs' },
  { to: '/jobs/new', label: 'Post a job' },
]

export function AppLayout() {
  const { isAuthenticated, user, logout, loginWithRedirect, error } = useAuth0()
  const location = useLocation()
  const { getMyBusiness } = useAuthedApi()
  const [business, setBusiness] = useState<Business | null>(null)

  useEffect(() => {
    if (!isAuthenticated) return
    getMyBusiness()
      .then(setBusiness)
      .catch(() => setBusiness(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated])

  // MCP Server reflects live shared infrastructure, not business-specific
  // data -- still gated the same as posting jobs (Prompt 16): don't even
  // render the link (let alone let it error) until the business is active.
  const navLinks = [
    ...BASE_NAV_LINKS,
    ...(business?.status === 'active' ? [{ to: '/mcp-server', label: 'MCP Server' }] : []),
    ...(PLATFORM_ADMIN_EMAIL && user?.email === PLATFORM_ADMIN_EMAIL
      ? [{ to: '/admin', label: 'Admin' }]
      : []),
  ]

  return (
    <div className="min-h-svh">
      <header className="border-b">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
          <nav className="flex items-center gap-4">
            <span className="font-semibold">FirstCall</span>
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={cn(
                  'text-sm text-muted-foreground hover:text-foreground',
                  location.pathname === link.to && 'text-foreground font-medium',
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>

          {isAuthenticated ? (
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">{user?.email}</span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
              >
                Log out
              </Button>
            </div>
          ) : (
            <Button size="sm" onClick={() => loginWithRedirect()}>
              Log in
            </Button>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-8">
        {error ? (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-destructive">
            <p className="font-medium">Auth0 error</p>
            <p className="text-sm">{error.message}</p>
          </div>
        ) : (
          <OnboardingGate />
        )}
      </main>
    </div>
  )
}
