import { BrowserRouter, Routes, Route } from 'react-router'
import { AppLayout } from '@/components/AppLayout'
import { withProtection } from '@/components/ProtectedRoute'
import { CandidatePipelinePage } from '@/pages/CandidatePipelinePage'
import { CandidateDetailPage } from '@/pages/CandidateDetailPage'
import { InterviewsPage } from '@/pages/InterviewsPage'

const ProtectedCandidatePipelinePage = withProtection(CandidatePipelinePage)
const ProtectedCandidateDetailPage = withProtection(CandidateDetailPage)
const ProtectedInterviewsPage = withProtection(InterviewsPage)

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<ProtectedCandidatePipelinePage />} />
          <Route path="/candidates/:id" element={<ProtectedCandidateDetailPage />} />
          <Route path="/interviews" element={<ProtectedInterviewsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
