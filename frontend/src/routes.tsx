import type { RouteObject } from 'react-router-dom'
import { Navigate } from 'react-router-dom'
import App from './App.tsx'
import Reporting from './pages/Reporting.tsx'
import CategoryPage from './pages/CategoryPage.tsx'
import SuitePage from './pages/SuitePage.tsx'
import RunDetail from './pages/RunDetail.tsx'
import Releases from './pages/Releases.tsx'
import ReleaseDetail from './pages/ReleaseDetail.tsx'
import ReferenceData from './pages/ReferenceData.tsx'
import EntityDetail from './pages/EntityDetail.tsx'
import Settings from './pages/Settings.tsx'
import NotFound from './pages/NotFound.tsx'
import ErrorPage from './pages/ErrorPage.tsx'
import LegacyRedirect from './components/LegacyRedirect.tsx'

/** The application route table. Exported so it can be unit-tested (matchRoutes)
 * without spinning up the browser router. */
export const routes: RouteObject[] = [
  {
    path: '/',
    element: <App />,
    errorElement: <ErrorPage />,
    children: [
      { index: true, element: <Navigate to="/reporting" replace /> },

      // Reporting — categories → suites → runs.
      { path: 'reporting', element: <Reporting /> },
      { path: 'reporting/:category', element: <CategoryPage /> },
      { path: 'reporting/suites/:workflowId', element: <SuitePage /> },
      { path: 'reporting/runs/:runId', element: <RunDetail /> },

      // Taxonomy Releases.
      { path: 'releases', element: <Releases /> },
      { path: 'releases/:snapshotId', element: <ReleaseDetail /> },

      // Reference Data.
      { path: 'reference', element: <ReferenceData /> },
      { path: 'reference/entities/:entityId', element: <EntityDetail /> },

      // Settings.
      { path: 'settings', element: <Settings /> },

      // --- Legacy paths → new homes (bare + parameterised, all eras) ---------
      { path: 'workflows', element: <Navigate to="/reporting" replace /> },
      {
        path: 'workflows/:workflowId',
        element: <LegacyRedirect to={(p) => `/reporting/suites/${p.workflowId}`} />,
      },
      {
        path: 'reporting/workflows/:workflowId',
        element: <LegacyRedirect to={(p) => `/reporting/suites/${p.workflowId}`} />,
      },
      { path: 'snapshots', element: <Navigate to="/releases" replace /> },
      {
        path: 'snapshots/:snapshotId',
        element: <LegacyRedirect to={(p) => `/releases/${p.snapshotId}`} />,
      },
      { path: 'runs', element: <Navigate to="/reporting" replace /> },
      {
        path: 'runs/:runId',
        element: <LegacyRedirect to={(p) => `/reporting/runs/${p.runId}`} />,
      },

      // Catch-all → styled in-shell 404.
      { path: '*', element: <NotFound /> },
    ],
  },
]
