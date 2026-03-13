import { useState, useEffect } from 'react'

interface TreeSummary {
  id: string
  question: string
  status: string
  total_claims: number
  verified_claims: number
  created_at: string
  finished_at: string | null
}

export default function HistoryPage() {
  const [trees, setTrees] = useState<TreeSummary[]>([])

  useEffect(() => {
    fetch('/api/trees')
      .then(r => r.json())
      .then(setTrees)
      .catch(console.error)
  }, [])

  return (
    <div className="p-6 max-w-4xl">
      <h2 className="text-xl font-semibold mb-6">Research History</h2>
      {trees.length === 0 ? (
        <p className="text-zinc-500">No research trees yet.</p>
      ) : (
        <div className="space-y-3">
          {trees.map(tree => (
            <div
              key={tree.id}
              className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 hover:border-zinc-700 transition-colors"
            >
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="font-medium text-sm">{tree.question}</h3>
                  <p className="text-xs text-zinc-500 mt-1">
                    {new Date(tree.created_at).toLocaleString()}
                  </p>
                </div>
                <StatusBadge status={tree.status} />
              </div>
              <div className="flex gap-4 mt-3 text-xs text-zinc-400">
                <span>Claims: {tree.total_claims}</span>
                <span className="text-emerald-400">Verified: {tree.verified_claims}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    converged: 'bg-emerald-500/20 text-emerald-400',
    running: 'bg-blue-500/20 text-blue-400',
    failed: 'bg-red-500/20 text-red-400',
    pending: 'bg-zinc-500/20 text-zinc-400',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${colors[status] || colors.pending}`}>
      {status}
    </span>
  )
}
