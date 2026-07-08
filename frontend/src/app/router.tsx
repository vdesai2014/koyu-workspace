import { createBrowserRouter, Navigate } from 'react-router-dom'

import App from './App'
import { ProjectDetailPage } from '../features/projects/pages/ProjectDetailPage'
import { ProjectsPage } from '../features/projects/pages/ProjectsPage'
import { RunDetailPage } from '../features/projects/pages/RunDetailPage'
import { DatasetsPage } from '../features/datasets/pages/DatasetsPage'
import { DatasetDetailPage } from '../features/datasets/DatasetDetailPage'
import { ControlsPage } from '../features/controls/pages/ControlsPage'
import { SyncJobsPage } from '../features/sync/pages/SyncJobsPage'

function LandingPage() {
  return (
    <section className="home-welcome">
      <p className="eyebrow">Local</p>
      <h1>Koyu robot learning workspace.</h1>
    </section>
  )
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <LandingPage /> },
      {
        path: 'projects',
        element: (
          <ProjectsPage
            scope="mine"
            title="Projects"
            description="Local projects across this machine, sorted and filterable by tag."
          />
        ),
      },
      { path: 'projects/:projectId', element: <ProjectDetailPage workspace={false} /> },
      { path: 'projects/:projectId/runs/:runId', element: <RunDetailPage workspace={false} /> },
      { path: 'datasets', element: <DatasetsPage /> },
      { path: 'datasets/:manifestId', element: <DatasetDetailPage /> },
      { path: 'controls', element: <ControlsPage /> },
      { path: 'sync', element: <SyncJobsPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
