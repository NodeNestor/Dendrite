import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import TreeView from '../components/TreeView'
import BranchDetail from '../components/BranchDetail'
import ProgressFeed from '../components/ProgressFeed'

interface ProgressEvent {
  tree_id: string
  branch_id: string
  event_type: string
  message: string
  data: Record<string, any>
  timestamp: string
}

interface ResearchPageProps {
  loadTreeId?: string | null
  onLoaded?: () => void
}

type RightPanel = 'feed' | 'branch' | 'synthesis'

export default function ResearchPage({ loadTreeId, onLoaded }: ResearchPageProps) {
  const [question, setQuestion] = useState('')
  const [treeId, setTreeId] = useState<string | null>(null)
  const [treeData, setTreeData] = useState<any>(null)
  const [selectedBranch, setSelectedBranch] = useState<string | null>(null)
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [rightPanel, setRightPanel] = useState<RightPanel>('feed')
  const wsRef = useRef<WebSocket | null>(null)
  const pollRef = useRef<number | null>(null)

  // Load a tree by ID (from history page)
  useEffect(() => {
    if (!loadTreeId) return
    const loadTree = async () => {
      try {
        const r = await fetch(`/api/tree/${loadTreeId}`)
        const tree = await r.json()
        if (!tree.error) {
          setTreeData(tree)
          setTreeId(loadTreeId)
          setQuestion(tree.question || '')
          setEvents([])
          setSelectedBranch(null)
          setLoading(false)
        }
      } catch {}
      onLoaded?.()
    }
    loadTree()
  }, [loadTreeId, onLoaded])

  const startResearch = async () => {
    if (!question.trim()) return
    setLoading(true)
    setEvents([])
    setTreeData(null)
    setSelectedBranch(null)
    setRightPanel('feed')

    try {
      const resp = await fetch('/api/research/async', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, max_depth: 4 }),
      })
      const data = await resp.json()
      setTreeId(data.tree_id)

      // Connect WebSocket for live updates
      const ws = new WebSocket(`ws://${window.location.host}/ws`)
      ws.onopen = () => ws.send(JSON.stringify({ tree_id: data.tree_id }))
      ws.onmessage = (e) => {
        const event: ProgressEvent = JSON.parse(e.data)
        if (event.event_type) {
          setEvents(prev => [...prev, event])
        }
      }
      wsRef.current = ws

      // Poll for tree data
      pollRef.current = window.setInterval(async () => {
        try {
          const r = await fetch(`/api/tree/${data.tree_id}`)
          const tree = await r.json()
          setTreeData(tree)
          if (tree.status === 'converged' || tree.status === 'failed') {
            setLoading(false)
            if (pollRef.current) clearInterval(pollRef.current)
          }
        } catch {}
      }, 2000)

    } catch (err) {
      console.error(err)
      setLoading(false)
    }
  }

  const stopResearch = async () => {
    if (!treeId) return
    try {
      await fetch(`/api/research/${treeId}/stop`, { method: 'POST' })
      setLoading(false)
      if (pollRef.current) clearInterval(pollRef.current)
    } catch (err) {
      console.error(err)
    }
  }

  const exportMarkdown = () => {
    if (treeId) window.open(`/api/tree/${treeId}/export/markdown`, '_blank')
  }

  const exportJson = () => {
    if (treeId) window.open(`/api/tree/${treeId}/export/json`, '_blank')
  }

  useEffect(() => {
    return () => {
      wsRef.current?.close()
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const handleBranchClick = useCallback((branchId: string) => {
    setSelectedBranch(branchId)
    setRightPanel('branch')
  }, [])

  // Parse synthesis for structured display
  const synthesisData = useMemo(() => {
    if (!treeData?.synthesis) return null
    try {
      return JSON.parse(treeData.synthesis)
    } catch {
      return null
    }
  }, [treeData?.synthesis])

  return (
    <div className="h-screen flex flex-col">
      {/* Top bar */}
      <div className="border-b border-zinc-800 p-4 flex gap-3 items-center">
        <input
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && startResearch()}
          placeholder="Ask a research question..."
          className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-4 py-2 text-sm
                     placeholder-zinc-500 focus:outline-none focus:border-emerald-500"
        />
        {loading ? (
          <button
            onClick={stopResearch}
            className="bg-red-600 hover:bg-red-500 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            Stop
          </button>
        ) : (
          <button
            onClick={startResearch}
            disabled={!question.trim()}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-700 disabled:text-zinc-500
                       text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            Investigate
          </button>
        )}

        {/* Export buttons */}
        {treeId && !loading && (
          <div className="flex gap-1">
            <button
              onClick={exportMarkdown}
              className="text-zinc-400 hover:text-zinc-200 text-xs px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700"
              title="Export as Markdown"
            >
              MD
            </button>
            <button
              onClick={exportJson}
              className="text-zinc-400 hover:text-zinc-200 text-xs px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700"
              title="Export as JSON"
            >
              JSON
            </button>
          </div>
        )}
      </div>

      {/* Content area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Tree visualization */}
        <div className="flex-1 relative">
          {treeData ? (
            <TreeView tree={treeData} onBranchClick={handleBranchClick} />
          ) : (
            <div className="flex items-center justify-center h-full text-zinc-500">
              {loading ? 'Building research tree...' : 'Enter a question to start'}
            </div>
          )}

          {/* Stats overlay */}
          {treeData && (
            <div className="absolute top-4 left-4 bg-zinc-900/90 border border-zinc-800 rounded-lg p-3 text-xs space-y-1">
              <div className="text-zinc-400">
                Claims: <span className="text-zinc-100">{treeData.total_claims || 0}</span>
              </div>
              <div className="text-emerald-400">
                Verified: {treeData.verified_claims || 0}
              </div>
              <div className="text-red-400">
                Refuted: {treeData.refuted_claims || 0}
              </div>
              <div className="text-amber-400">
                Contested: {treeData.contested_claims || 0}
              </div>
              <div className="text-zinc-400">
                Branches: {Object.keys(treeData.branches || {}).length}
              </div>
              {treeData.refinement_pass > 0 && (
                <div className="text-cyan-400">
                  Refined: {treeData.refinement_pass}x
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right panel */}
        <div className="w-96 border-l border-zinc-800 flex flex-col overflow-hidden">
          {/* Panel tabs */}
          <div className="flex border-b border-zinc-800 shrink-0">
            <PanelTab active={rightPanel === 'feed'} onClick={() => { setRightPanel('feed'); setSelectedBranch(null) }}>
              Feed
            </PanelTab>
            {treeData?.synthesis && (
              <PanelTab active={rightPanel === 'synthesis'} onClick={() => { setRightPanel('synthesis'); setSelectedBranch(null) }}>
                Report
              </PanelTab>
            )}
            {selectedBranch && (
              <PanelTab active={rightPanel === 'branch'} onClick={() => setRightPanel('branch')}>
                Branch
              </PanelTab>
            )}
          </div>

          {/* Panel content */}
          {rightPanel === 'branch' && selectedBranch && treeData?.branches?.[selectedBranch] ? (
            <BranchDetail
              branch={treeData.branches[selectedBranch]}
              onClose={() => { setSelectedBranch(null); setRightPanel('feed') }}
            />
          ) : rightPanel === 'synthesis' && treeData?.synthesis ? (
            <SynthesisView synthesis={treeData.synthesis} data={synthesisData} />
          ) : (
            <ProgressFeed events={events} />
          )}
        </div>
      </div>
    </div>
  )
}

function PanelTab({ active, onClick, children }: {
  active: boolean; onClick: () => void; children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 text-xs py-2 transition-colors ${
        active
          ? 'text-zinc-100 border-b-2 border-emerald-500'
          : 'text-zinc-500 hover:text-zinc-300'
      }`}
    >
      {children}
    </button>
  )
}

function SynthesisView({ synthesis, data }: { synthesis: string; data: any }) {
  if (data && typeof data === 'object') {
    return (
      <div className="h-full overflow-y-auto p-4 space-y-4">
        {data.title && (
          <h3 className="text-sm font-semibold text-zinc-100">{data.title}</h3>
        )}
        {data.summary && (
          <p className="text-xs text-zinc-300 leading-relaxed">{data.summary}</p>
        )}
        {data.confidence_overall != null && (
          <div className="text-xs">
            <span className="text-zinc-400">Overall confidence: </span>
            <span className={
              data.confidence_overall >= 0.7 ? 'text-emerald-400' :
              data.confidence_overall >= 0.4 ? 'text-amber-400' : 'text-red-400'
            }>
              {(data.confidence_overall * 100).toFixed(0)}%
            </span>
          </div>
        )}

        {data.sections?.map((section: any, i: number) => (
          <div key={i} className="border-l-2 border-zinc-700 pl-3">
            <h4 className="text-xs font-medium text-zinc-200">{section.heading}</h4>
            <p className="text-xs text-zinc-400 leading-relaxed mt-1">{section.body}</p>
            {section.citations?.length > 0 && (
              <div className="mt-1 space-y-0.5">
                {section.citations.map((url: string, j: number) => (
                  <a key={j} href={url} target="_blank" rel="noopener noreferrer"
                     className="block text-[9px] text-zinc-600 hover:text-zinc-400 truncate">
                    {url}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}

        {data.verified_conclusions?.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-emerald-400 mb-1">Verified Conclusions</h4>
            {data.verified_conclusions.map((c: string, i: number) => (
              <p key={i} className="text-xs text-zinc-300 pl-2 border-l border-emerald-500/30 mb-1">{c}</p>
            ))}
          </div>
        )}

        {data.contested_points?.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-amber-400 mb-1">Contested Points</h4>
            {data.contested_points.map((c: string, i: number) => (
              <p key={i} className="text-xs text-zinc-300 pl-2 border-l border-amber-500/30 mb-1">{c}</p>
            ))}
          </div>
        )}

        {data.open_questions?.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-zinc-400 mb-1">Open Questions</h4>
            {data.open_questions.map((q: string, i: number) => (
              <p key={i} className="text-xs text-zinc-500 pl-2 border-l border-zinc-600 mb-1">{q}</p>
            ))}
          </div>
        )}
      </div>
    )
  }

  // Fallback: raw text
  return (
    <div className="h-full overflow-y-auto p-4">
      <h4 className="text-xs text-zinc-400 uppercase tracking-wider mb-2">Synthesis Report</h4>
      <p className="text-xs text-zinc-300 whitespace-pre-wrap leading-relaxed">{synthesis}</p>
    </div>
  )
}
