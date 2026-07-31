import { BrowserRouter, Routes, Route } from 'react-router'
import { JobListPage } from '@/pages/JobListPage'
import { JobDetailPage } from '@/pages/JobDetailPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<JobListPage />} />
        <Route path="/jobs/:id" element={<JobDetailPage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
