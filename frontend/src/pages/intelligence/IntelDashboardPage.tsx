import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { intelApi } from '@/api/intel'
import { ontologyApi } from '@/api/ontologies'
import type { OntologyListItem } from '@/types/ontology'
import { DANGER_LABELS, DANGER_COLORS } from '@/types/intel'
import { Send, Loader2, Shield, Link2, Crosshair, Zap, Search, Brain, Undo2 } from 'lucide-react'
import cytoscape from 'cytoscape'

const TYPE_COLORS: Record<string, string> = {
  Organization: '#7c3aed', Facility: '#2563eb', Product: '#059669',
  Material: '#d97706', Process: '#db2777', Document: '#ea580c',
  Category: '#0891b2', Concept: '#4f46e5', Weapon: '#dc2626', Unit: '#e11d48',
}
const FALLBACK_COLORS = ['#2563eb','#059669','#dc2626','#7c3aed','#d97706','#0891b2','#db2777','#4f46e5','#65a30d','#be123c']

function nodeColor(labels: string[]): string {
  for (const l of labels) { if (TYPE_COLORS[l]) return TYPE_COLORS[l] }
  let hash = 0
  for (let i = 0; i < (labels[0] || 'Entity').length; i += 1) hash = ((hash << 5) - hash + (labels[0] || 'Entity').charCodeAt(i)) | 0
  return FALLBACK_COLORS[Math.abs(hash) % FALLBACK_COLORS.length]
}

// ── Result types ─────────────────────────────────────────────────────
interface QuickResult {
  ontology_id: string; ontology_name: string
  matched_entities: Array<{ id: string; name_cn: string; type: string; match_keyword: string; confidence: number }>
  triggered_rules: Array<{ id: string; name_cn: string; formula: string; linked_entities: string[] }>
  triggered_actions: Array<{ id: string; name_cn: string; execution_rule: string; function_code: string }>
  danger_level: string; danger_score: number; recommendations: string[]; mode: string
}

// ── DangerGauge ──────────────────────────────────────────────────────
function DangerGauge({ score, level }: { score: number; level: string }) {
  const color = DANGER_COLORS[level] || '#6b7280'
  const angle = Math.min((score / 100) * 180, 180)
  const rad = (angle * Math.PI) / 180
  const r = 80; const cx = 100; const cy = 100
  const nx = cx + r * Math.cos(Math.PI - rad)
  const ny = cy - r * Math.sin(Math.PI - rad)
  const largeArc = angle > 90 ? 1 : 0
  return (
    <div className="flex flex-col items-center">
      <svg width="160" height="100" viewBox="0 0 200 120">
        <path d="M20,100 A80,80 0 0,1 180,100" fill="none" stroke="#e5e7eb" strokeWidth="18" strokeLinecap="round" />
        {score > 0 && <path d={`M20,100 A80,80 0 ${largeArc},1 ${nx},${ny}`} fill="none" stroke={color} strokeWidth="18" strokeLinecap="round" />}
        <line x1={cx} y1={cy} x2={nx || 20} y2={ny || 100} stroke="#1f2937" strokeWidth="2" />
        <circle cx={cx} cy={cy} r="4" fill="#1f2937" />
      </svg>
      <div className="text-2xl font-bold -mt-2" style={{ color }}>{score}</div>
      <div className="text-xs font-medium" style={{ color }}>{DANGER_LABELS[level] || level}</div>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────
export default function IntelDashboardPage() {
  const navigate = useNavigate()
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)

  // State
  const [ontologies, setOntologies] = useState<OntologyListItem[]>([])
  const [selectedOid, setSelectedOid] = useState<string>('')
  const [intelText, setIntelText] = useState('')
  const [quickResult, setQuickResult] = useState<QuickResult | null>(null)
  const [quickLoading, setQuickLoading] = useState(false)
  const [deepLoading, setDeepLoading] = useState(false)
  const [graphData, setGraphData] = useState<{ nodes: any[]; edges: any[] } | null>(null)
  const [lastDeepExtractTime, setLastDeepExtractTime] = useState<string | null>(null)

  // ── Load ontology list ──────────────────────────────────────────
  useEffect(() => {
    ontologyApi.list({ page_size: 200 }).then((d: any) => {
      const items = d?.items || []
      setOntologies(items)
      if (!selectedOid && items.length > 0) setSelectedOid(items[0].id)
    })
  }, [])

  useEffect(() => {
    if (!selectedOid) return
    intelApi.getGraph(selectedOid).then((g: any) => setGraphData(g)).catch(() => {})
  }, [selectedOid])

  // ── Layer 1: Quick Assess ───────────────────────────────────────
  const handleQuickAssess = async () => {
    if (!selectedOid || !intelText.trim() || quickLoading) return
    setQuickLoading(true)
    setQuickResult(null)
    try {
      const res = await intelApi.assessQuick(selectedOid, intelText.trim()) as any
      setQuickResult(res)
    } catch (err: any) {
      alert(err?.detail || err?.message || '评估失败')
    } finally {
      setQuickLoading(false)
    }
  }

  // ── Layer 2: Deep Extraction (async in background) ──────────────
  const handleDeepExtract = async () => {
    if (!selectedOid || !intelText.trim() || deepLoading) return
    setDeepLoading(true)
    try {
      const extractStartTime = new Date().toISOString()
      await intelApi.submit(selectedOid, intelText.trim())
      setLastDeepExtractTime(extractStartTime)
      // Poll for completion
      let count = 0
      const check = async () => {
        if (count >= 60) { setDeepLoading(false); return }
        count++
        try {
          const g = await intelApi.getGraph(selectedOid) as any
          const prevNodeCount = graphData?.nodes?.length || 0
          const newNodeCount = g?.nodes?.length || 0
          // Simple heuristic: if graph grew or polled enough times, assume done
          if (newNodeCount !== prevNodeCount || count > 15) {
            setGraphData(g)
            setDeepLoading(false)
            // Also refresh quick assess if there's still intel text
            if (quickResult) {
              const refreshed = await intelApi.assessQuick(selectedOid, intelText.trim()) as any
              setQuickResult(refreshed)
            }
          } else {
            setTimeout(check, 3000)
          }
        } catch {
          setTimeout(check, 3000)
        }
      }
      setTimeout(check, 5000) // wait 5s before first poll
    } catch (err: any) {
      alert(err?.detail || err?.message || '深度抽取失败')
      setDeepLoading(false)
    }
  }

  // ── Undo last deep extraction ──────────────────────────────────
  const handleUndo = async () => {
    if (!selectedOid) return
    if (!confirm('确定要撤回最近一次的深度抽取操作吗？新增的实体和关系将被删除。')) return
    try {
      const res = await intelApi.undoLast(selectedOid) as any
      alert(res.message || '已撤回')
      setLastDeepExtractTime(null)
      // Refresh graph
      const g = await intelApi.getGraph(selectedOid) as any
      setGraphData(g)
    } catch (err: any) {
      alert(err?.detail || err?.message || '撤回失败')
    }
  }

  // ── Cytoscape graph ─────────────────────────────────────────────
  useEffect(() => {
    if (!graphData?.nodes?.length || !containerRef.current) return
    if (cyRef.current) { cyRef.current.destroy(); cyRef.current = null }
    const cy = cytoscape({
      container: containerRef.current,
      elements: [
        ...graphData.nodes.map((n: any) => {
          const createdAt = n.properties?.created_at
          const isNew = lastDeepExtractTime && createdAt && createdAt > lastDeepExtractTime
          return {
            data: {
              id: n.id,
              label: n.properties?.name_cn || n.id?.slice(0, 8) || '?',
              typeLabel: n.labels?.[0] || 'Entity',
              isNew: isNew,
            },
            style: {
              'background-color': nodeColor(n.labels || []),
              label: String(n.properties?.name_cn || n.id?.slice(0, 8) || ''),
              'font-size': '9px', 'text-valign': 'bottom', 'text-halign': 'center',
              'text-wrap': 'ellipsis', 'text-max-width': '80px',
              'border-width': isNew ? 4 : 2,
              'border-color': isNew ? '#f59e0b' : '#fff',
              'width': isNew ? 36 : 28,
              'height': isNew ? 36 : 28,
            },
          }
        }),
        ...(graphData.edges || []).map((e: any) => ({
          data: { id: e.id, source: e.source, target: e.target, label: e.type },
        })),
      ],
      style: [
        { selector: 'node', style: { width: 28, height: 28, 'border-width': 2, 'border-color': '#fff' } },
        { selector: 'edge', style: { width: 1, 'line-color': '#94a3b8', 'target-arrow-color': '#94a3b8', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'font-size': 7, label: 'data(label)' } },
      ],
      layout: { name: 'cose', animate: false, nodeRepulsion: () => 4000, idealEdgeLength: () => 80 },
    })
    cyRef.current = cy
    return () => { cy.destroy(); cyRef.current = null }
  }, [graphData])

  // ── Render ──────────────────────────────────────────────────────
  const selectedOnt = ontologies.find(o => o.id === selectedOid)

  return (
    <div className="h-full flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Crosshair size={20} /> 军事动态情报分析演示
        </h2>
      </div>

      {/* Top: Ontology selector + Intel input */}
      <div className="flex gap-3 items-start">
        <div className="flex flex-col gap-1 min-w-[200px]">
          <label className="text-xs text-gray-500 font-medium">知识本体</label>
          <select
            value={selectedOid}
            onChange={e => { setSelectedOid(e.target.value); setQuickResult(null) }}
            className="border rounded-lg px-3 py-2 text-sm"
          >
            {ontologies.map(o => (
              <option key={o.id} value={o.id}>
                {o.name} ({o.entity_count}实体/{o.relation_count}关系)
              </option>
            ))}
          </select>
          {selectedOnt && (
            <span className="text-[10px] text-gray-400">
              领域:{selectedOnt.domain} · 状态:{selectedOnt.status}
            </span>
          )}
        </div>

        <div className="flex-1 flex gap-2 items-end">
          <textarea
            value={intelText}
            onChange={e => setIntelText(e.target.value)}
            placeholder="输入实时军事情报文本..."
            rows={2}
            className="flex-1 border rounded-lg px-3 py-2 text-sm resize-none"
          />
          <div className="flex flex-col gap-1">
            <button
              onClick={handleQuickAssess}
              disabled={!selectedOid || !intelText.trim() || quickLoading}
              className="shrink-0 flex items-center gap-1.5 px-4 py-2 bg-black text-white rounded-lg text-sm disabled:opacity-50"
            >
              {quickLoading ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
              快速评估
            </button>
            <button
              onClick={handleDeepExtract}
              disabled={!selectedOid || !intelText.trim() || deepLoading}
              className="shrink-0 flex items-center gap-1.5 px-4 py-2 border border-gray-300 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-50"
            >
              {deepLoading ? <Loader2 size={14} className="animate-spin" /> : <Brain size={14} />}
              深度抽取
            </button>
            <button
              onClick={handleUndo}
              disabled={!selectedOid}
              className="shrink-0 flex items-center gap-1.5 px-3 py-2 border border-red-200 rounded-lg text-sm text-red-600 hover:bg-red-50 disabled:opacity-50"
              title="撤回最近一次深度抽取的新增实体"
            >
              <Undo2 size={14} />
              撤回
            </button>
          </div>
        </div>
      </div>

      {/* Main area: Results + Graph */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* Left: Graph */}
        <div className="flex-1 bg-white border rounded-lg relative min-h-[300px]">
          {!graphData?.nodes?.length ? (
            <div className="absolute inset-0 flex items-center justify-center text-gray-400 text-sm">
              {selectedOid ? '知识本体暂无实体' : '请先选择一个知识本体'}
            </div>
          ) : null}
          <div ref={containerRef} className="absolute inset-0" />
        </div>

        {/* Right: Results */}
        <div className="w-[320px] flex flex-col gap-3 shrink-0 overflow-y-auto">
          {/* Danger gauge */}
          {quickResult && (
            <div className="bg-white border rounded-lg p-3 flex flex-col items-center">
              <DangerGauge score={quickResult.danger_score} level={quickResult.danger_level} />
              <span className="text-[10px] text-gray-400 mt-1">
                {quickResult.mode === 'baseline' ? '无匹配实体 · 基线评估' : `匹配 ${quickResult.matched_entities.length} 个实体`}
              </span>
            </div>
          )}

          {/* Triggered Actions */}
          {quickResult && quickResult.triggered_actions.length > 0 && (
            <div className="bg-white border rounded-lg p-3">
              <h3 className="text-sm font-semibold mb-2 flex items-center gap-1">
                <Zap size={14} className="text-amber-500" /> 触发动作
              </h3>
              {quickResult.triggered_actions.map((a, i) => (
                <div key={i} className="mb-2 p-2 bg-amber-50 rounded text-xs">
                  <div className="font-medium text-amber-800">{a.name_cn}</div>
                  {a.execution_rule && <div className="text-amber-600 mt-0.5">{a.execution_rule}</div>}
                </div>
              ))}
            </div>
          )}

          {/* Recommendations */}
          {quickResult && quickResult.recommendations.length > 0 && (
            <div className="bg-white border rounded-lg p-3">
              <h3 className="text-sm font-semibold mb-2 flex items-center gap-1">
                <Shield size={14} /> 战术建议
              </h3>
              <ol className="space-y-1.5">
                {quickResult.recommendations.map((r, i) => (
                  <li key={i} className="text-xs flex gap-2">
                    <span className="font-bold text-gray-400">{i + 1}.</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Matched entities */}
          {quickResult && quickResult.matched_entities.length > 0 && (
            <div className="bg-white border rounded-lg p-3">
              <h3 className="text-sm font-semibold mb-2 flex items-center gap-1">
                <Search size={14} /> 匹配实体 ({quickResult.matched_entities.length})
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {quickResult.matched_entities.map((e, i) => (
                  <span key={i} className="inline-flex items-center gap-1 px-2 py-1 bg-blue-50 border border-blue-200 rounded text-[11px] text-blue-700">
                    {e.name_cn}
                    <span className="text-blue-400">({e.type})</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Loading / empty states */}
          {quickLoading && (
            <div className="bg-white border rounded-lg p-6 text-center text-gray-400">
              <Loader2 size={24} className="animate-spin mx-auto mb-2" />
              <span className="text-xs">匹配已有知识本体...</span>
            </div>
          )}
          {!quickResult && !quickLoading && (
            <div className="bg-white border rounded-lg p-6 text-center text-gray-400 text-xs">
              选择一个知识本体，输入情报文本，点击「快速评估」
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
