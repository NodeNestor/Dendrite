interface ClaimCardProps {
  claim: any
}

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  verified: { bg: 'bg-emerald-500/10 border-emerald-500/30', text: 'text-emerald-400', label: 'VERIFIED' },
  accepted: { bg: 'bg-sky-500/10 border-sky-500/30', text: 'text-sky-400', label: 'ACCEPTED' },
  refuted: { bg: 'bg-red-500/10 border-red-500/30', text: 'text-red-400', label: 'REFUTED' },
  contested: { bg: 'bg-amber-500/10 border-amber-500/30', text: 'text-amber-400', label: 'CONTESTED' },
  pending: { bg: 'bg-zinc-500/10 border-zinc-500/30', text: 'text-zinc-400', label: 'PENDING' },
}

const SOURCE_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  peer_reviewed: { label: 'Peer Reviewed', color: 'text-emerald-400 bg-emerald-500/10' },
  preprint: { label: 'Preprint', color: 'text-blue-400 bg-blue-500/10' },
  academic: { label: 'Academic', color: 'text-violet-400 bg-violet-500/10' },
  encyclopedia: { label: 'Encyclopedia', color: 'text-sky-400 bg-sky-500/10' },
  news: { label: 'News', color: 'text-zinc-300 bg-zinc-500/10' },
  blog: { label: 'Blog', color: 'text-orange-400 bg-orange-500/10' },
  forum: { label: 'Forum', color: 'text-red-400 bg-red-500/10' },
  web: { label: 'Web', color: 'text-zinc-400 bg-zinc-500/10' },
}

export default function ClaimCard({ claim }: ClaimCardProps) {
  const style = STATUS_STYLES[claim.status] || STATUS_STYLES.pending

  // Get best source type from evidence
  const bestEvidence = claim.evidence_for?.[0]
  const sourceType = bestEvidence?.source_type || 'web'
  const sourceQuality = bestEvidence?.source_quality || 0
  const stLabel = SOURCE_TYPE_LABELS[sourceType] || SOURCE_TYPE_LABELS.web

  return (
    <div className={`border rounded-md p-3 ${style.bg}`}>
      <div className="flex justify-between items-start gap-2">
        <p className="text-xs text-zinc-200 leading-relaxed">{claim.content}</p>
        <span className={`text-[9px] font-bold shrink-0 ${style.text}`}>
          {style.label}
        </span>
      </div>

      <div className="flex flex-wrap gap-2 mt-2 text-[10px] text-zinc-500">
        <span>Confidence: {(claim.confidence * 100).toFixed(0)}%</span>
        <span>Sources: {claim.source_urls?.length || 0}</span>
        {claim.evidence_for?.length > 0 && (
          <span className="text-emerald-500">{claim.evidence_for.length} supporting</span>
        )}
        {claim.evidence_against?.length > 0 && (
          <span className="text-red-500">{claim.evidence_against.length} against</span>
        )}
      </div>

      {/* Source quality badges */}
      <div className="flex gap-1.5 mt-2">
        <span className={`text-[9px] px-1.5 py-0.5 rounded ${stLabel.color}`}>
          {stLabel.label}
        </span>
        {sourceQuality > 0 && (
          <span className={`text-[9px] px-1.5 py-0.5 rounded ${
            sourceQuality >= 0.7 ? 'text-emerald-400 bg-emerald-500/10' :
            sourceQuality >= 0.4 ? 'text-amber-400 bg-amber-500/10' :
            'text-red-400 bg-red-500/10'
          }`}>
            Quality: {(sourceQuality * 100).toFixed(0)}%
          </span>
        )}
      </div>

      {/* Status history */}
      {claim.status_history?.length > 0 && (
        <div className="mt-2 space-y-0.5">
          {claim.status_history.slice(-3).map((entry: string, i: number) => (
            <div key={i} className="text-[9px] text-zinc-600 italic">
              {entry}
            </div>
          ))}
        </div>
      )}

      {claim.source_urls?.length > 0 && (
        <div className="mt-2 space-y-0.5">
          {claim.source_urls.slice(0, 3).map((url: string, i: number) => (
            <a
              key={i}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="block text-[10px] text-zinc-500 hover:text-zinc-300 truncate"
            >
              {url}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
