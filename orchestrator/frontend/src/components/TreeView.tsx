import { useMemo, useCallback } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  type NodeTypes,
  Handle,
  Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

interface TreeViewProps {
  tree: any
  onBranchClick: (branchId: string) => void
}

// Branch type colors
const TYPE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  investigation: { bg: '#0c4a6e', border: '#0284c7', text: '#7dd3fc' },
  verification: { bg: '#164e3e', border: '#059669', text: '#6ee7b7' },
  deepening: { bg: '#4a1d96', border: '#7c3aed', text: '#c4b5fd' },
  counter: { bg: '#7c2d12', border: '#ea580c', text: '#fdba74' },
  resolution: { bg: '#701a3e', border: '#db2777', text: '#f9a8d4' },
}

function BranchNode({ data }: { data: any }) {
  const colors = TYPE_COLORS[data.branch_type] || TYPE_COLORS.investigation

  const verified = data.claims?.filter((c: any) => c.status === 'verified').length || 0
  const refuted = data.claims?.filter((c: any) => c.status === 'refuted').length || 0
  const contested = data.claims?.filter((c: any) => c.status === 'contested').length || 0
  const total = data.claims?.length || 0

  return (
    <div
      onClick={() => data.onClick?.(data.id)}
      className="cursor-pointer rounded-lg border px-3 py-2 min-w-[180px] max-w-[260px] shadow-lg"
      style={{ backgroundColor: colors.bg, borderColor: colors.border }}
    >
      <Handle type="target" position={Position.Top} className="!bg-zinc-500" />

      <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: colors.text }}>
        {data.branch_type}
      </div>
      <div className="text-xs text-zinc-100 leading-tight line-clamp-2">
        {data.question}
      </div>

      {total > 0 && (
        <div className="flex gap-2 mt-2 text-[10px]">
          <span className="text-zinc-400">{total} claims</span>
          {verified > 0 && <span className="text-emerald-400">{verified}✓</span>}
          {refuted > 0 && <span className="text-red-400">{refuted}✗</span>}
          {contested > 0 && <span className="text-amber-400">{contested}?</span>}
        </div>
      )}

      {data.converged && (
        <div className="text-[9px] text-zinc-500 mt-1 truncate">
          {data.convergence_reason}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} className="!bg-zinc-500" />
    </div>
  )
}

const nodeTypes: NodeTypes = {
  branch: BranchNode,
}

export default function TreeView({ tree, onBranchClick }: TreeViewProps) {
  const { nodes, edges } = useMemo(() => {
    if (!tree?.branches || !tree.root_branch_id) return { nodes: [], edges: [] }

    const nodes: Node[] = []
    const edges: Edge[] = []
    const positions = new Map<string, { x: number; y: number }>()

    // BFS to layout the tree
    const queue: Array<{ id: string; depth: number; index: number; parentIndex: number }> = []
    const depthCounts = new Map<number, number>()

    // Count nodes at each depth first
    function countDepths(branchId: string, depth: number) {
      depthCounts.set(depth, (depthCounts.get(depth) || 0) + 1)
      const branch = tree.branches[branchId]
      if (branch?.child_branch_ids) {
        for (const childId of branch.child_branch_ids) {
          countDepths(childId, depth + 1)
        }
      }
    }
    countDepths(tree.root_branch_id, 0)

    // Layout
    const depthIndices = new Map<number, number>()
    function layoutBranch(branchId: string, depth: number) {
      const branch = tree.branches[branchId]
      if (!branch) return

      const count = depthCounts.get(depth) || 1
      const index = depthIndices.get(depth) || 0
      depthIndices.set(depth, index + 1)

      const spacing = 300
      const x = (index - (count - 1) / 2) * spacing
      const y = depth * 180

      positions.set(branchId, { x, y })

      nodes.push({
        id: branchId,
        type: 'branch',
        position: { x, y },
        data: {
          ...branch,
          id: branchId,
          onClick: onBranchClick,
        },
      })

      if (branch.parent_branch_id) {
        edges.push({
          id: `${branch.parent_branch_id}-${branchId}`,
          source: branch.parent_branch_id,
          target: branchId,
          style: { stroke: '#52525b', strokeWidth: 1.5 },
          animated: !branch.converged,
        })
      }

      if (branch.child_branch_ids) {
        for (const childId of branch.child_branch_ids) {
          layoutBranch(childId, depth + 1)
        }
      }
    }

    layoutBranch(tree.root_branch_id, 0)

    return { nodes, edges }
  }, [tree, onBranchClick])

  if (!nodes.length) {
    return <div className="flex items-center justify-center h-full text-zinc-500">No tree data</div>
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      minZoom={0.2}
      maxZoom={2}
      proOptions={{ hideAttribution: true }}
    >
      <Background color="#27272a" gap={20} />
      <Controls className="!bg-zinc-900 !border-zinc-800 !text-zinc-400" />
    </ReactFlow>
  )
}
