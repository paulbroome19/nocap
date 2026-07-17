import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import Workflows from './pages/Workflows.tsx'
import WorkflowDetail from './pages/WorkflowDetail.tsx'
import Snapshots from './pages/Snapshots.tsx'
import Runs from './pages/Runs.tsx'
import RunDetail from './pages/RunDetail.tsx'

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/workflows" replace /> },
      { path: 'workflows', element: <Workflows /> },
      { path: 'workflows/:workflowId', element: <WorkflowDetail /> },
      { path: 'snapshots', element: <Snapshots /> },
      { path: 'runs', element: <Runs /> },
      { path: 'runs/:runId', element: <RunDetail /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
