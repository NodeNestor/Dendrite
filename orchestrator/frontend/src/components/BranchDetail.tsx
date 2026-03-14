import { useState, useMemo } from 'react'
import ClaimCard from './ClaimCard'

interface BranchDetailProps {
  branch: any
  onClose: () => void
}

type StatusFilter = 'all' | 'verified' | 'accepted' | 'refuted' | 'contested' | 'pending'

export default function BranchDetail({ branch, onClose }: BranchDetailProps) {
  const [searchText, setSearchText] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  const typeColors: Record<string, string> = {
    investigation: 'text-sky-400',
    verification: 'text-emerald-400',
    deepening: 'text-violet-400',
    counter: 'text-orange-400',
    resolution: 'text-pink-400',
  }

  const filteredClaims = useMemo(() => {
    if (!branch.claims) return []
    return branch.claims.filter((claim: any) => {
      if (statusFilter !== 'all' && claim.status !== statusFilter) return false
      if (searchText && !claim.content.toLowerCase().includes(searchText.toLowerCase())) return false
      return true
    })
  }, [branch.claims, statusFilter, searchText])

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { all: 0 }
    for (const claim of branch.claims || []) {
      counts.all = (counts.all || 0) + 1
      counts[claim.status] = (counts[claim.status] || 0) + 1
    }
    return counts
  }, [branch.claims])

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-zinc-800 shrink-0">
        <div className="flex justify-between items-start">
          <div>
            <div className={`text-[10px] uppercase tracking-wider ${typeColors[branch.branch_type] || 'text-zinc-400'}`}>
              {branch.branch_type}
            </div>
            <h3 className="text-sm font-medium mt-1">{branch.question}</h3>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 text-lg leading-none">&times;</button>
        </div>

        <div className="flex gap-4 mt-3 text-xs text-zinc-400">
          <span>Depth: {branch.depth}</span>
          <span>Iterations: {branch.iteration}</span>
          <span>Pages: {branch.pages_fetched}</span>
        </div>

        {branch.converged && (
          <div className="mt-2 text-xs text-zinc-500">
            Converged: {branch.convergence_reason}
          </div>
        )}
      </div>

      {/* Search & Filter */}
      <div className="p-3 border-b border-zinc-800 space-y-2 shrink-0">
        <input
          type="text"
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
          placeholder="Search claims..."
          className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-xs
                     placeholder-zinc-500 focus:outline-none focus:border-emerald-500"
        />
        <div className="flex gap-1 flex-wrap">
          {(['all', 'verified', 'accepted', 'refuted', 'contested', 'pending'] as StatusFilter[]).map(status => {
            const count = statusCounts[status] || 0
            if (status !== 'all' && count === 0) return null
            const colors: Record<string, string> = {
              all: 'text-zinc-300 bg-zinc-700',
              verified: 'text-emerald-400 bg-emerald-500/20',
              accepted: 'text-sky-400 bg-sky-500/20',
              refuted: 'text-red-400 bg-red-500/20',
              contested: 'text-amber-400 bg-amber-500/20',
              pending: 'text-zinc-400 bg-zinc-500/20',
            }
            return (
              <button
                key={status}
                onClick={() => setStatusFilter(status)}
                className={`text-[10px] px-2 py-0.5 rounded-full transition-opacity ${
                  colors[status]
                } ${statusFilter === status ? 'opacity-100' : 'opacity-50 hover:opacity-75'}`}
              >
                {status} ({count})
              </button>
            )
          })}
        </div>
      </div>

      {/* Claims list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        <h4 className="text-xs text-zinc-400 uppercase tracking-wider mb-2">
          Claims ({filteredClaims.length}{filteredClaims.length !== (branch.claims?.length || 0) ? ` / ${branch.claims?.length || 0}` : ''})
        </h4>
        {filteredClaims.length ? (
          filteredClaims.map((claim: any) => (
            <ClaimCard key={claim.id} claim={claim} />
          ))
        ) : (
          <p className="text-xs text-zinc-500">
            {branch.claims?.length ? 'No matching claims' : 'No claims yet'}
          </p>
        )}
      </div>
    </div>
  )
}
