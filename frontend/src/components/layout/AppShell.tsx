import { useEffect, useState, type PropsWithChildren } from 'react'

import { Sidebar } from './Sidebar'

const SIDEBAR_KEY = 'koyu_sidebar_collapsed'

export function AppShell({ children }: PropsWithChildren) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(SIDEBAR_KEY) === '1')

  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0')
  }, [collapsed])

  return (
    <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((value) => !value)} />
      <main className="app-main">{children}</main>
    </div>
  )
}
