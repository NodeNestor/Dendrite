import { useState, useEffect } from 'react'

export default function SettingsPage() {
  const [config, setConfig] = useState<Record<string, any>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch('/api/config')
      .then(r => r.json())
      .then(setConfig)
      .catch(console.error)
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      const resp = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      const data = await resp.json()
      setConfig(data)
    } catch (err) {
      console.error(err)
    }
    setSaving(false)
  }

  const groups = [
    {
      title: 'Bulk Model',
      fields: ['bulk_provider', 'bulk_model', 'bulk_api_url', 'bulk_api_key', 'bulk_max_tokens'],
    },
    {
      title: 'Synthesis Model',
      fields: ['synthesis_provider', 'synthesis_model', 'synthesis_api_url', 'synthesis_api_key', 'synthesis_max_tokens'],
    },
    {
      title: 'Services',
      fields: ['searxng_url', 'hivemind_url'],
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
  ]

  return (
    <div className="p-6 max-w-2xl">
      <h2 className="text-xl font-semibold mb-6">Settings</h2>
      <div className="space-y-6">
        {groups.map(group => (
          <div key={group.title} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <h3 className="text-sm font-medium text-zinc-300 mb-3">{group.title}</h3>
            <div className="space-y-2">
              {group.fields.map(field => (
                <div key={field} className="flex items-center gap-3">
                  <label className="text-xs text-zinc-400 w-48 shrink-0">{field}</label>
                  <input
                    type={typeof config[field] === 'number' ? 'number' : 'text'}
                    value={config[field] ?? ''}
                    onChange={e => setConfig(prev => ({
                      ...prev,
                      [field]: typeof prev[field] === 'number' ? Number(e.target.value) : e.target.value,
                    }))}
                    className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-xs
                               focus:outline-none focus:border-emerald-500"
                  />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <button
        onClick={save}
        disabled={saving}
        className="mt-6 bg-emerald-600 hover:bg-emerald-500 text-white px-5 py-2 rounded-lg text-sm font-medium"
      >
        {saving ? 'Saving...' : 'Save'}
      </button>
    </div>
  )
}
