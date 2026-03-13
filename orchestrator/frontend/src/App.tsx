import { useState } from 'react'
import ResearchPage from './pages/ResearchPage'
import HistoryPage from './pages/HistoryPage'
import SettingsPage from './pages/SettingsPage'

type Page = 'research' | 'history' | 'settings'

export default function App() {
  const [page, setPage] = useState<Page>('research')

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex">
      {/* Sidebar */}
      <nav className="w-56 bg-zinc-900 border-r border-zinc-800 p-4 flex flex-col gap-1">
        <h1 className="text-lg font-bold text-emerald-400 mb-6 tracking-tight">
          Dendrite
        </h1>
        <NavButton active={page === 'research'} onClick={() => setPage('research')}>
          Research
        </NavButton>
        <NavButton active={page === 'history'} onClick={() => setPage('history')}>
          History
        </NavButton>
        <NavButton active={page === 'settings'} onClick={() => setPage('settings')}>
          Settings
        </NavButton>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-hidden">
        {page === 'research' && <ResearchPage />}
        {page === 'history' && <HistoryPage />}
        {page === 'settings' && <SettingsPage />}
      </main>
    </div>
  )
}

function NavButton({ active, onClick, children }: {
  active: boolean; onClick: () => void; children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={`text-left px-3 py-2 rounded-md text-sm transition-colors ${
        active
          ? 'bg-zinc-800 text-zinc-100'
          : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
      }`}
    >
      {children}
    </button>
  )
}
