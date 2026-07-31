import { BrowserRouter, Routes, Route } from 'react-router'
import { AppLayout } from '@/components/AppLayout'
import { withProtection } from '@/components/ProtectedRoute'
import { CandidatePipelinePage } from '@/pages/CandidatePipelinePage'
import { CandidateDetailPage } from '@/pages/CandidateDetailPage'
import { InterviewsPage } from '@/pages/InterviewsPage'
import { PostJobPage } from '@/pages/PostJobPage'
import { BusinessesPage } from '@/pages/BusinessesPage'

const ProtectedCandidatePipelinePage = withProtection(CandidatePipelinePage)
const ProtectedCandidateDetailPage = withProtection(CandidateDetailPage)
const ProtectedInterviewsPage = withProtection(InterviewsPage)
const ProtectedPostJobPage = withProtection(PostJobPage)
const ProtectedBusinessesPage = withProtection(BusinessesPage)

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<ProtectedCandidatePipelinePage />} />
          <Route path="/candidates/:id" element={<ProtectedCandidateDetailPage />} />
          <Route path="/interviews" element={<ProtectedInterviewsPage />} />
          <Route path="/jobs/new" element={<ProtectedPostJobPage />} />
          <Route path="/businesses" element={<ProtectedBusinessesPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
