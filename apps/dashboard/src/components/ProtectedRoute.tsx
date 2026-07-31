import { withAuthenticationRequired } from '@auth0/auth0-react'
import type { ComponentType } from 'react'

export function withProtection<P extends object>(Component: ComponentType<P>) {
  return withAuthenticationRequired(Component, {
    onRedirecting: () => (
      <div className="flex min-h-svh items-center justify-center text-muted-foreground">
        Redirecting to login...
      </div>
    ),
  })
}
