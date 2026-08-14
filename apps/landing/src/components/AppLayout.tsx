import { Link, Outlet } from 'react-router'

export function AppLayout() {
  return (
    <div className="min-h-svh">
      <header className="border-b">
        <div className="mx-auto max-w-2xl px-4 py-3">
          <Link to="/" className="text-lg font-semibold">
            FirstCall Careers
          </Link>
        </div>
      </header>

      <Outlet />
    </div>
  )
}
