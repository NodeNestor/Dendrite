import { useRef, useEffect } from 'react'

interface ProgressEvent {
  tree_id: string
  branch_id: string
  event_type: string
  message: string
  data: Record<string, any>
  timestamp: string
}

const EVENT_COLORS: Record<string, string> = {
  tree_started: 'text-sky-400',
  branch_started: 'text-violet-400',
  claims_extracted: 'text-emerald-400',
  claim_triaged: 'text-amber-400',
  branch_converged: 'text-zinc-400',
  validation_started: 'text-orange-400',
  synthesis_started: 'text-pink-400',
  tree_complete: 'text-emerald-400',
  tree_failed: 'text-red-400',
}

export default function ProgressFeed({ events }: { events: ProgressEvent[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  return (
    <div className="h-full flex flex-col">
      <div className="p-4 border-b border-zinc-800 shrink-0">
        <h4 className="text-xs text-zinc-400 uppercase tracking-wider">Live Feed</h4>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-1.5">
        {events.length === 0 ? (
          <p className="text-xs text-zinc-500">Waiting for events...</p>
        ) : (
          events.map((event, i) => (
            <div key={i} className="text-xs leading-relaxed">
              <span className={EVENT_COLORS[event.event_type] || 'text-zinc-400'}>
                [{event.event_type}]
              </span>{' '}
              <span className="text-zinc-300">{event.message}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
