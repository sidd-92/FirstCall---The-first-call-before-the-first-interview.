import { BrowserRouter, Routes, Route } from 'react-router'
import { AppLayout } from '@/components/AppLayout'
import { JobListPage } from '@/pages/JobListPage'
import { JobDetailPage } from '@/pages/JobDetailPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<JobListPage />} />
          <Route path="/jobs/:id" element={<JobDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
