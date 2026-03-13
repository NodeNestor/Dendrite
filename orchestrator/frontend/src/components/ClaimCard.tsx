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

export default function ClaimCard({ claim }: ClaimCardProps) {
  const style = STATUS_STYLES[claim.status] || STATUS_STYLES.pending

  return (
    <div className={`border rounded-md p-3 ${style.bg}`}>
      <div className="flex justify-between items-start gap-2">
        <p className="text-xs text-zinc-200 leading-relaxed">{claim.content}</p>
        <span className={`text-[9px] font-bold shrink-0 ${style.text}`}>
          {style.label}
        </span>
      </div>

      <div className="flex gap-3 mt-2 text-[10px] text-zinc-500">
        <span>Confidence: {(claim.confidence * 100).toFixed(0)}%</span>
        <span>Sources: {claim.source_urls?.length || 0}</span>
        {claim.evidence_for?.length > 0 && (
          <span className="text-emerald-500">{claim.evidence_for.length} supporting</span>
        )}
        {claim.evidence_against?.length > 0 && (
          <span className="text-red-500">{claim.evidence_against.length} against</span>
        )}
      </div>

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
