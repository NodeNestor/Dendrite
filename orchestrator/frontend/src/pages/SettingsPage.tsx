import { useState, useEffect } from 'react'

export default function SettingsPage() {
  const [config, setConfig] = useState<Record<string, any>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    fetch('/api/config')
      .then(r => r.json())
      .then(setConfig)
      .catch(console.error)
  }, [])

  const save = async () => {
    setSaving(true)
    setSaved(false)
    try {
      const resp = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      const data = await resp.json()
      setConfig(data)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      console.error(err)
    }
    setSaving(false)
  }

  const groups = [
    {
      title: 'Bulk Model',
      description: 'Small, fast model for claim extraction and triage',
      fields: ['bulk_provider', 'bulk_model', 'bulk_api_url', 'bulk_api_key', 'bulk_max_tokens'],
    },
    {
      title: 'Synthesis Model',
      description: 'Larger model for cross-validation and final reports',
      fields: ['synthesis_provider', 'synthesis_model', 'synthesis_api_url', 'synthesis_api_key', 'synthesis_max_tokens'],
    },
    {
      title: 'Services',
      fields: ['searxng_url', 'hivemind_url'],
    },
    {
      title: 'Academic Providers',
      description: 'arXiv and Semantic Scholar for scholarly sources',
      fields: ['enable_arxiv', 'enable_semantic_scholar', 'semantic_scholar_api_key'],
    },
    {
      title: 'Tree Structure',
      fields: ['max_depth', 'max_branch_iterations', 'verification_iterations', 'queries_per_iteration'],
    },
    {
      title: 'Search Width',
      fields: ['urls_per_iteration', 'results_per_provider', 'max_concurrent_fetches', 'max_concurrent_llm'],
    },
    {
      title: 'Verification',
      fields: ['verification_threshold', 'min_independent_sources', 'max_concurrent_verifications', 'verification_fetch_count'],
    },
    {
      title: 'Convergence',
      fields: ['min_convergence_iterations', 'diminishing_returns_threshold', 'coverage_target'],
    },
    {
      title: 'Source Quality',
      description: 'How much source authority affects claim confidence',
      fields: ['source_quality_weight', 'recency_weight'],
    },
    {
      title: 'Semantic Deduplication',
      description: 'TF-IDF cosine similarity threshold for detecting duplicate claims',
      fields: ['semantic_dedup_threshold'],
    },
    {
      title: 'Fetch Cache',
      description: 'In-memory cache for fetched pages to avoid re-downloading',
      fields: ['fetch_cache_size', 'fetch_cache_ttl'],
    },
    {
      title: 'Contradiction Resolution',
      description: 'Automatic resolution of conflicting evidence',
      fields: ['enable_contradiction_resolution', 'resolution_iterations'],
    },
    {
      title: 'Multi-Turn Refinement',
      description: 'Self-critique and follow-up research after initial synthesis',
      fields: ['enable_refinement', 'max_refinement_passes'],
    },
    {
      title: 'HiveMindDB Feedback',
      description: 'Store verified claims for future research',
      fields: ['enable_hivemind_feedback'],
    },
  ]

  return (
    <div className="h-full overflow-y-auto p-6 flex flex-col items-center">
    <div className="w-full max-w-3xl">
      <h2 className="text-xl font-semibold mb-6">Settings</h2>
      <div className="space-y-6">
        {groups.map(group => (
          <div key={group.title} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <h3 className="text-sm font-medium text-zinc-300 mb-1">{group.title}</h3>
            {'description' in group && group.description && (
              <p className="text-xs text-zinc-500 mb-3">{group.description}</p>
            )}
            <div className="space-y-2">
              {group.fields.map(field => {
                const value = config[field]
                const isBool = typeof value === 'boolean'

                return (
                  <div key={field} className="flex items-center gap-3">
                    <label className="text-xs text-zinc-400 w-52 shrink-0">{field}</label>
                    {isBool ? (
                      <button
                        onClick={() => setConfig(prev => ({ ...prev, [field]: !prev[field] }))}
                        className={`text-xs px-3 py-1 rounded transition-colors ${
                          value
                            ? 'bg-emerald-600/20 text-emerald-400 border border-emerald-500/30'
                            : 'bg-zinc-800 text-zinc-500 border border-zinc-700'
                        }`}
                      >
                        {value ? 'Enabled' : 'Disabled'}
                      </button>
                    ) : (
                      <input
                        type={typeof value === 'number' ? 'number' : 'text'}
                        step={typeof value === 'number' && value < 1 ? '0.01' : undefined}
                        value={config[field] ?? ''}
                        onChange={e => setConfig(prev => ({
                          ...prev,
                          [field]: typeof prev[field] === 'number' ? Number(e.target.value) : e.target.value,
                        }))}
                        className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-xs
                                   focus:outline-none focus:border-emerald-500"
                      />
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>
      <button
        onClick={save}
        disabled={saving}
        className="mt-6 bg-emerald-600 hover:bg-emerald-500 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
      >
        {saving ? 'Saving...' : saved ? 'Saved!' : 'Save'}
      </button>
    </div>
    </div>
  )
}
