import { BrowserRouter, Routes, Route } from 'react-router'
import { AppLayout } from '@/components/AppLayout'
import { withProtection } from '@/components/ProtectedRoute'
import { CandidatePipelinePage } from '@/pages/CandidatePipelinePage'
import { CandidateDetailPage } from '@/pages/CandidateDetailPage'
import { InterviewsPage } from '@/pages/InterviewsPage'
import { PostJobPage } from '@/pages/PostJobPage'
import { JobPostingsPage } from '@/pages/JobPostingsPage'
import { JobPostingDetailPage } from '@/pages/JobPostingDetailPage'
import { BusinessesPage } from '@/pages/BusinessesPage'
import { McpServerPage } from '@/pages/McpServerPage'

const ProtectedCandidatePipelinePage = withProtection(CandidatePipelinePage)
const ProtectedCandidateDetailPage = withProtection(CandidateDetailPage)
const ProtectedInterviewsPage = withProtection(InterviewsPage)
const ProtectedPostJobPage = withProtection(PostJobPage)
const ProtectedJobPostingsPage = withProtection(JobPostingsPage)
const ProtectedJobPostingDetailPage = withProtection(JobPostingDetailPage)
const ProtectedBusinessesPage = withProtection(BusinessesPage)
const ProtectedMcpServerPage = withProtection(McpServerPage)

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<ProtectedCandidatePipelinePage />} />
          <Route path="/candidates/:id" element={<ProtectedCandidateDetailPage />} />
          <Route path="/interviews" element={<ProtectedInterviewsPage />} />
          <Route path="/jobs" element={<ProtectedJobPostingsPage />} />
          <Route path="/jobs/new" element={<ProtectedPostJobPage />} />
          <Route path="/jobs/:id" element={<ProtectedJobPostingDetailPage />} />
          <Route path="/businesses" element={<ProtectedBusinessesPage />} />
          <Route path="/mcp-server" element={<ProtectedMcpServerPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
