import { useAuth0 } from '@auth0/auth0-react'
import { Link, Outlet, useLocation } from 'react-router'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const NAV_LINKS = [
  { to: '/', label: 'Candidates' },
  { to: '/interviews', label: 'Interviews' },
  { to: '/jobs/new', label: 'Post a job' },
  { to: '/businesses', label: 'Businesses' },
]

export function AppLayout() {
  const { isAuthenticated, user, logout, loginWithRedirect, error } = useAuth0()
  const location = useLocation()

  return (
    <div className="min-h-svh">
      <header className="border-b">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
          <nav className="flex items-center gap-4">
            <span className="font-semibold">FirstCall</span>
            {NAV_LINKS.map((link) => (
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
          <Outlet />
        )}
      </main>
    </div>
  )
}
