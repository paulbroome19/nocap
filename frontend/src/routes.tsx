import type { RouteObject } from 'react-router-dom'
import { Navigate } from 'react-router-dom'
import App from './App.tsx'
import Reporting from './pages/Reporting.tsx'
import RegulatorReporting from './pages/RegulatorReporting.tsx'
import CategoryPage from './pages/CategoryPage.tsx'
import SuitePage from './pages/SuitePage.tsx'
import RunLayout from './pages/run/RunLayout.tsx'
import RunCover from './pages/run/RunCover.tsx'
import RunInput from './pages/run/RunInput.tsx'
import RunIndicators from './pages/run/RunIndicators.tsx'
import RunValidation from './pages/run/RunValidation.tsx'
import RunPackage from './pages/run/RunPackage.tsx'
import Regulators from './pages/Regulators.tsx'
import RegulatorReleases from './pages/RegulatorReleases.tsx'
import ReleaseWizard from './pages/ReleaseWizard.tsx'
import ReleaseDetail from './pages/ReleaseDetail.tsx'
import ReferenceData from './pages/ReferenceData.tsx'
import EntitySetup from './pages/EntitySetup.tsx'
import EntityDetail from './pages/EntityDetail.tsx'
import FilingIndicators from './pages/FilingIndicators.tsx'
import Parameters from './pages/Parameters.tsx'
import Settings from './pages/Settings.tsx'
import SettingsReporting from './pages/SettingsReporting.tsx'
import SettingsActiveReporting from './pages/SettingsActiveReporting.tsx'
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

      // Reporting — regulator → categories → suites → runs.
      { path: 'reporting', element: <Reporting /> },
      { path: 'reporting/:regulatorCode', element: <RegulatorReporting /> },
      { path: 'reporting/:regulatorCode/:category', element: <CategoryPage /> },
      { path: 'reporting/suites/:workflowId', element: <SuitePage /> },
      // A run is a submission-instance cover with per-stage sub-pages.
      {
        path: 'reporting/runs/:runId',
        element: <RunLayout />,
        children: [
          { index: true, element: <RunCover /> },
          { path: 'input', element: <RunInput /> },
          { path: 'indicators', element: <RunIndicators /> },
          { path: 'validation', element: <RunValidation /> },
          { path: 'package', element: <RunPackage /> },
        ],
      },

      // Taxonomies — regulator (publisher) → its releases → release detail.
      { path: 'releases', element: <Regulators /> },
      { path: 'releases/regulators/:regulatorId', element: <RegulatorReleases /> },
      { path: 'releases/regulators/:regulatorId/new', element: <ReleaseWizard /> },
      // Static "regulators" segment outranks this dynamic release id.
      { path: 'releases/:snapshotId', element: <ReleaseDetail /> },

      // Reference Data — three entity-anchored tables.
      { path: 'reference', element: <ReferenceData /> },
      { path: 'reference/entities', element: <EntitySetup /> },
      { path: 'reference/entities/:entityId', element: <EntityDetail /> },
      { path: 'reference/filing-indicators', element: <FilingIndicators /> },
      { path: 'reference/parameters', element: <Parameters /> },

      // Settings — sections → Reporting → regulator → active-reporting editor.
      { path: 'settings', element: <Settings /> },
      { path: 'settings/reporting', element: <SettingsReporting /> },
      {
        path: 'settings/reporting/:regulatorCode',
        element: <SettingsActiveReporting />,
      },

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
