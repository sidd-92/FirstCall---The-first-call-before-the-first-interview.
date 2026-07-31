import { createRoot } from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import './index.css'
import App from './App.tsx'

const domain = import.meta.env.VITE_AUTH0_DOMAIN as string
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID as string
// Requesting an access token scoped to the backend's audience is what makes
// getAccessTokenSilently() return a JWT the backend can verify -- without it
// Auth0 issues an opaque token that isn't valid as a Bearer token here.
const audience = import.meta.env.VITE_AUTH0_AUDIENCE as string | undefined

// No <StrictMode> here: it double-invokes effects in dev, which makes
// Auth0Provider process the OAuth callback's one-time-use `code` twice --
// the second attempt fails, isAuthenticated never flips to true, and
// withAuthenticationRequired immediately redirects to /authorize again,
// looping on the consent screen forever.
//
// cacheLocation 'localstorage' + useRefreshTokens keep the session alive
// across page refreshes: tokens persist in localStorage instead of memory,
// and getAccessTokenSilently() swaps the stored refresh token for a new
// access token without a redirect -- so the Auth0 consent screen stops
// appearing on every reload. Requires "Allow Offline Access" and "Refresh
// Token Rotation" enabled in the Auth0 dashboard for this SPA application.
createRoot(document.getElementById('root')!).render(
  <Auth0Provider
    domain={domain}
    clientId={clientId}
    cacheLocation="localstorage"
    useRefreshTokens
    authorizationParams={{
      redirect_uri: window.location.origin,
      audience,
    }}
  >
    <App />
  </Auth0Provider>,
)
