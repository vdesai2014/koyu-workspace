import { Outlet } from 'react-router-dom'

import { AppShell } from '../components/layout/AppShell'
import { IntroTour } from '../components/tour/IntroTour'

export default function App() {
  return (
    <AppShell>
      <Outlet />
      <IntroTour />
    </AppShell>
  )
}
