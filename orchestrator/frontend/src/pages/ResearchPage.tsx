import { useState, useEffect, useRef, useCallback } from 'react'
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

export default function ResearchPage({ loadTreeId, onLoaded }: ResearchPageProps) {
  const [question, setQuestion] = useState('')
  const [treeId, setTreeId] = useState<string | null>(null)
  const [treeData, setTreeData] = useState<any>(null)
  const [selectedBranch, setSelectedBranch] = useState<string | null>(null)
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [loading, setLoading] = useState(false)
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

  useEffect(() => {
    return () => {
      wsRef.current?.close()
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const handleBranchClick = useCallback((branchId: string) => {
    setSelectedBranch(branchId)
  }, [])

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
        <button
          onClick={startResearch}
          disabled={loading || !question.trim()}
          className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-zinc-700 disabled:text-zinc-500
                     text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {loading ? 'Investigating...' : 'Investigate'}
        </button>
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
            </div>
          )}
        </div>

        {/* Right panel — branch detail or progress feed */}
        <div className="w-96 border-l border-zinc-800 flex flex-col overflow-hidden">
          {selectedBranch && treeData?.branches?.[selectedBranch] ? (
            <BranchDetail
              branch={treeData.branches[selectedBranch]}
              onClose={() => setSelectedBranch(null)}
            />
          ) : (
            <ProgressFeed events={events} />
          )}
        </div>
      </div>
    </div>
  )
}
