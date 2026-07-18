import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import Reporting from './pages/Reporting.tsx'
import WorkflowDetail from './pages/WorkflowDetail.tsx'
import RunDetail from './pages/RunDetail.tsx'
import Releases from './pages/Releases.tsx'
import ReleaseDetail from './pages/ReleaseDetail.tsx'
import ReferenceData from './pages/ReferenceData.tsx'
import EntityDetail from './pages/EntityDetail.tsx'

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/reporting" replace /> },

      // Reporting — workflows & runs.
      { path: 'reporting', element: <Reporting /> },
      { path: 'reporting/workflows/:workflowId', element: <WorkflowDetail /> },
      { path: 'reporting/runs/:runId', element: <RunDetail /> },

      // Releases — DPM & taxonomy artifacts.
      { path: 'releases', element: <Releases /> },
      { path: 'releases/:snapshotId', element: <ReleaseDetail /> },

      // Reference Data — entities & per-workflow config.
      { path: 'reference', element: <ReferenceData /> },
      { path: 'reference/entities/:entityId', element: <EntityDetail /> },

      // Legacy paths → new homes.
      { path: 'workflows', element: <Navigate to="/reporting" replace /> },
      { path: 'snapshots', element: <Navigate to="/releases" replace /> },
      { path: 'runs', element: <Navigate to="/reporting" replace /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
