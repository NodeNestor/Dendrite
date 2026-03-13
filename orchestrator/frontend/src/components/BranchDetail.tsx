import ClaimCard from './ClaimCard'

interface BranchDetailProps {
  branch: any
  onClose: () => void
}

export default function BranchDetail({ branch, onClose }: BranchDetailProps) {
  const typeColors: Record<string, string> = {
    investigation: 'text-sky-400',
    verification: 'text-emerald-400',
    deepening: 'text-violet-400',
    counter: 'text-orange-400',
  }

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

      {/* Claims list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        <h4 className="text-xs text-zinc-400 uppercase tracking-wider mb-2">
          Claims ({branch.claims?.length || 0})
        </h4>
        {branch.claims?.length ? (
          branch.claims.map((claim: any) => (
            <ClaimCard key={claim.id} claim={claim} />
          ))
        ) : (
          <p className="text-xs text-zinc-500">No claims yet</p>
        )}
      </div>
    </div>
  )
}
