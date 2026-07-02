import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { intelApi } from '@/api/intel'
import { DANGER_LABELS, DANGER_COLORS } from '@/types/intel'
import { Send, Loader2, Shield, Link2, Crosshair, Zap, Search, Brain, Undo2, Lightbulb, Check, X } from 'lucide-react'
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
  const [activeOid, setActiveOid] = useState<string>('')
  const [activeOntName, setActiveOntName] = useState<string>('')
  const [intelText, setIntelText] = useState('')
  const [quickResult, setQuickResult] = useState<QuickResult | null>(null)
  const [quickLoading, setQuickLoading] = useState(false)
  const [deepLoading, setDeepLoading] = useState(false)
  const [autoForwardLoading, setAutoForwardLoading] = useState(false)
  const [graphData, setGraphData] = useState<{ nodes: any[]; edges: any[] } | null>(null)
  const [lastDeepExtractTime, setLastDeepExtractTime] = useState<string | null>(null)
  const [suggestLoading, setSuggestLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<{
    suggested_rules: Array<{ name_cn: string; formula: string; description: string; linked_entities: string[] }>
    suggested_actions: Array<{ name_cn: string; execution_rule: string; description: string; linked_entities: string[] }>
  } | null>(null)
  const [approving, setApproving] = useState<string | null>(null)

  // ── 自动匹配辅助函数 ──────────────────────────────────────────
  const autoMatchAndSet = async (text: string): Promise<string | null> => {
    try {
      const res = await intelApi.autoMatch(text) as any
      if (res.matched && res.best_ontology_id) {
        setActiveOid(res.best_ontology_id)
        setActiveOntName(res.best_ontology_name)
        // 加载图谱
        const g = await intelApi.getGraph(res.best_ontology_id) as any
        setGraphData(g)
        return res.best_ontology_id
      }
      return null
    } catch {
      return null
    }
  }

  // ── Layer 1: Quick Assess（自动匹配本体）───────────────────────
  const handleQuickAssess = async () => {
    if (!intelText.trim() || quickLoading) return
    setQuickLoading(true)
    setQuickResult(null)
    try {
      const oid = await autoMatchAndSet(intelText.trim())
      if (!oid) { alert('未能在任何本体中匹配到实体'); setQuickLoading(false); return }
      const res = await intelApi.assessQuick(oid, intelText.trim()) as any
      setQuickResult(res)
    } catch (err: any) {
      alert(err?.detail || err?.message || '评估失败')
    } finally {
      setQuickLoading(false)
    }
  }

  // ── Layer 2: Deep Extraction（自动匹配本体）────────────────────
  const handleDeepExtract = async () => {
    if (!intelText.trim() || deepLoading) return
    setDeepLoading(true)
    try {
      const oid = await autoMatchAndSet(intelText.trim())
      if (!oid) { alert('未能在任何本体中匹配到实体'); setDeepLoading(false); return }
      const extractStartTime = new Date().toISOString()
      await intelApi.submit(oid, intelText.trim())
      setLastDeepExtractTime(extractStartTime)
      let count = 0
      const check = async () => {
        if (count >= 60) { setDeepLoading(false); return }
        count++
        try {
          const g = await intelApi.getGraph(oid) as any
          setGraphData(g)
          setDeepLoading(false)
          if (quickResult) {
            const refreshed = await intelApi.assessQuick(oid, intelText.trim()) as any
            setQuickResult(refreshed)
          }
        } catch {
          setTimeout(check, 3000)
        }
      }
      setTimeout(check, 5000)
    } catch (err: any) {
      alert(err?.detail || err?.message || '深度抽取失败')
      setDeepLoading(false)
    }
  }

  // ── Auto Forward：自动匹配本体 + 分析 + 转发 ─────────────────
  const handleAutoForward = async () => {
    if (!intelText.trim() || autoForwardLoading) return
    setAutoForwardLoading(true)
    setQuickResult(null)
    try {
      const res = await intelApi.autoForward(intelText.trim()) as any
      if (res.matched) {
        setActiveOid(res.best_ontology_id)
        setActiveOntName(res.best_ontology_name)
        setQuickResult(res.payload)
        const g = await intelApi.getGraph(res.best_ontology_id) as any
        setGraphData(g)
      } else {
        alert(res.message || '未能在任何本体中匹配到实体')
      }
    } catch (err: any) {
      alert(err?.detail || err?.message || '自动转发失败')
    } finally {
      setAutoForwardLoading(false)
    }
  }

  // ── Undo last deep extraction ──────────────────────────────────
  const handleUndo = async () => {
    if (!activeOid) return
    if (!confirm('确定要撤回最近一次的深度抽取操作吗？新增的实体和关系将被删除。')) return
    try {
      const res = await intelApi.undoLast(activeOid) as any
      alert(res.message || '已撤回')
      setLastDeepExtractTime(null)
      const g = await intelApi.getGraph(activeOid) as any
      setGraphData(g)
    } catch (err: any) {
      alert(err?.detail || err?.message || '撤回失败')
    }
  }

  // ── Rule Suggestions ────────────────────────────────────────────
  const handleSuggestRules = async () => {
    if (!activeOid) return
    setSuggestLoading(true)
    setSuggestions(null)
    try {
      const res = await intelApi.suggestRules(activeOid) as any
      setSuggestions(res.suggestions || null)
      if (!res.suggestions?.suggested_rules?.length && !res.suggestions?.suggested_actions?.length) {
        alert(res.message || '没有可建议的新规则')
      }
    } catch (err: any) {
      alert(err?.detail || err?.message || '建议生成失败')
    } finally {
      setSuggestLoading(false)
    }
  }

  const handleApproveRule = async (rule: any) => {
    if (!activeOid) return
    setApproving(rule.name_cn)
    try {
      await intelApi.approveRule(activeOid, rule)
      setSuggestions(prev => prev ? {
        ...prev,
        suggested_rules: prev.suggested_rules.filter((r: any) => r.name_cn !== rule.name_cn),
      } : null)
    } catch (err: any) { alert(err?.detail || '采纳失败') }
    finally { setApproving(null) }
  }

  const handleApproveAction = async (action: any) => {
    if (!activeOid) return
    setApproving(action.name_cn)
    try {
      await intelApi.approveAction(activeOid, action)
      setSuggestions(prev => prev ? {
        ...prev,
        suggested_actions: prev.suggested_actions.filter((a: any) => a.name_cn !== action.name_cn),
      } : null)
    } catch (err: any) { alert(err?.detail || '采纳失败') }
    finally { setApproving(null) }
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
  return (
    <div className="h-full flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-slate-800 to-slate-600 flex items-center justify-center shadow-sm">
            <Crosshair size={18} className="text-white" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-800">军事动态情报分析</h2>
            <p className="text-xs text-slate-400">输入情报文本，系统自动匹配知识本体并评估威胁</p>
          </div>
        </div>
        {activeOntName && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            <span className="text-xs font-medium text-emerald-700">{activeOntName}</span>
          </div>
        )}
      </div>

      {/* Intel input card */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
        <div className="flex gap-3 items-start">
          <div className="flex-1 relative">
            <textarea
              value={intelText}
              onChange={e => setIntelText(e.target.value)}
              placeholder="输入实时军事情报文本，系统将自动匹配最佳知识本体..."
              rows={3}
              className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400 transition-all placeholder:text-slate-300"
            />
            <span className="absolute bottom-2 right-3 text-[10px] text-slate-300">
              {intelText.length > 0 ? `${intelText.length} 字` : ''}
            </span>
          </div>
          <div className="flex flex-col gap-2">
            <button
              onClick={handleQuickAssess}
              disabled={!intelText.trim() || quickLoading}
              className="shrink-0 flex items-center gap-2 px-5 py-2.5 bg-slate-800 text-white rounded-xl text-sm font-medium hover:bg-slate-700 disabled:opacity-40 transition-all shadow-sm"
            >
              {quickLoading ? <Loader2 size={15} className="animate-spin" /> : <Zap size={15} />}
              快速评估
            </button>
            <button
              onClick={handleAutoForward}
              disabled={!intelText.trim() || autoForwardLoading}
              className="shrink-0 flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-blue-600 to-blue-500 text-white rounded-xl text-sm font-medium hover:from-blue-700 hover:to-blue-600 disabled:opacity-40 transition-all shadow-sm"
            >
              {autoForwardLoading ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
              智能转发
            </button>
            <div className="flex gap-2">
              <button
                onClick={handleDeepExtract}
                disabled={!intelText.trim() || deepLoading}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 border border-slate-200 rounded-xl text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-40 transition-colors"
              >
                {deepLoading ? <Loader2 size={12} className="animate-spin" /> : <Brain size={12} />}
                深度抽取
              </button>
              <button
                onClick={handleUndo}
                disabled={!activeOid}
                className="flex items-center justify-center gap-1 px-3 py-2 border border-red-100 rounded-xl text-xs text-red-500 hover:bg-red-50 disabled:opacity-40 transition-colors"
                title="撤回最近一次深度抽取的新增实体"
              >
                <Undo2 size={12} />
              </button>
              <button
                onClick={handleSuggestRules}
                disabled={!activeOid || suggestLoading}
                className="flex items-center justify-center gap-1 px-3 py-2 border border-amber-100 rounded-xl text-xs text-amber-600 hover:bg-amber-50 disabled:opacity-40 transition-colors"
                title="LLM 分析历史情报，归纳建议新规则"
              >
                {suggestLoading ? <Loader2 size={12} className="animate-spin" /> : <Lightbulb size={12} />}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main area: Results + Graph */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* Left: Graph */}
        <div className="flex-1 bg-white rounded-2xl border border-slate-200 shadow-sm relative overflow-hidden min-h-[300px]">
          {!graphData?.nodes?.length && !quickLoading && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 z-10 pointer-events-none">
              <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center">
                <Search size={28} className="text-slate-300" />
              </div>
              <span className="text-sm text-slate-300 font-medium">输入情报后自动展示知识图谱</span>
            </div>
          )}
          {quickLoading && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 z-10 pointer-events-none">
              <Loader2 size={32} className="animate-spin text-blue-400" />
              <span className="text-sm text-slate-400">正在匹配知识本体...</span>
            </div>
          )}
          <div ref={containerRef} className="absolute inset-0" />
        </div>

        {/* Right: Results panel */}
        <div className="w-[340px] flex flex-col gap-3 shrink-0 overflow-y-auto">
          {/* Danger gauge */}
          {quickResult && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 flex flex-col items-center">
              <DangerGauge score={quickResult.danger_score} level={quickResult.danger_level} />
              <div className="flex items-center gap-2 mt-2">
                <span className={`w-2 h-2 rounded-full ${
                  quickResult.danger_level === 'critical' ? 'bg-red-500' :
                  quickResult.danger_level === 'high' ? 'bg-orange-500' :
                  quickResult.danger_level === 'medium' ? 'bg-yellow-500' : 'bg-green-500'
                }`} />
                <span className="text-xs text-slate-400">
                  {quickResult.mode === 'baseline' ? '无匹配实体 · 基线评估' : `匹配 ${quickResult.matched_entities.length} 个实体 · ${quickResult.triggered_rules.length} 条规则`}
                </span>
              </div>
            </div>
          )}

          {/* Triggered Actions */}
          {quickResult && quickResult.triggered_actions.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
              <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                <div className="w-6 h-6 rounded-lg bg-amber-100 flex items-center justify-center">
                  <Zap size={13} className="text-amber-600" />
                </div>
                触发动作 · {quickResult.triggered_actions.length}
              </h3>
              <div className="space-y-2 max-h-[200px] overflow-y-auto">
                {quickResult.triggered_actions.map((a, i) => (
                  <div key={i} className="p-3 bg-amber-50/50 border border-amber-100 rounded-xl text-xs">
                    <div className="font-semibold text-amber-800">{a.name_cn}</div>
                    {a.execution_rule && (
                      <div className="text-amber-600 mt-1 leading-relaxed">{a.execution_rule}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recommendations */}
          {quickResult && quickResult.recommendations.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
              <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                <div className="w-6 h-6 rounded-lg bg-blue-100 flex items-center justify-center">
                  <Shield size={13} className="text-blue-600" />
                </div>
                战术建议
              </h3>
              <div className="space-y-2">
                {quickResult.recommendations.map((r, i) => (
                  <div key={i} className="flex items-start gap-2.5 px-3 py-2 rounded-xl bg-slate-50 text-xs">
                    <span className="shrink-0 w-5 h-5 rounded-full bg-slate-200 flex items-center justify-center text-[10px] font-bold text-slate-500">{i + 1}</span>
                    <span className="text-slate-600 leading-relaxed">{r}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Matched entities */}
          {quickResult && quickResult.matched_entities.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
              <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                <div className="w-6 h-6 rounded-lg bg-purple-100 flex items-center justify-center">
                  <Search size={13} className="text-purple-600" />
                </div>
                匹配实体
              </h3>
              <div className="flex flex-wrap gap-2">
                {quickResult.matched_entities.map((e, i) => (
                  <span key={i} className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-gradient-to-r from-purple-50 to-blue-50 border border-purple-100 rounded-xl text-xs text-purple-700 font-medium">
                    {e.name_cn}
                    <span className="text-[10px] text-purple-400 bg-purple-100 px-1 py-0.5 rounded-md">{e.type}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Loading state */}
          {quickLoading && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 flex flex-col items-center gap-3">
              <Loader2 size={28} className="animate-spin text-blue-400" />
              <span className="text-xs text-slate-400 font-medium">正在匹配知识本体并分析威胁...</span>
            </div>
          )}
        </div>
      </div>

      {/* Suggestions panel */}
      {suggestions && (suggestions.suggested_rules?.length > 0 || suggestions.suggested_actions?.length > 0) && (
        <div className="bg-gradient-to-r from-amber-50 to-yellow-50 border border-amber-200 rounded-2xl p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-amber-800 mb-4 flex items-center gap-2">
            <div className="w-7 h-7 rounded-xl bg-amber-200 flex items-center justify-center">
              <Lightbulb size={14} className="text-amber-700" />
            </div>
            LLM 归纳建议 · 基于历史情报生成的规则与动作
          </h3>
          <div className="grid grid-cols-2 gap-4">
            {suggestions.suggested_rules?.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-amber-700 mb-3 uppercase tracking-wide">新增规则</h4>
                <div className="space-y-3">
                  {suggestions.suggested_rules.map((r: any, i: number) => (
                    <div key={i} className="bg-white rounded-xl border border-amber-100 p-3.5 shadow-sm">
                      <div className="font-semibold text-amber-800 text-sm mb-1.5">{r.name_cn}</div>
                      <code className="block text-xs text-slate-500 bg-slate-50 rounded-lg p-2 mb-2 font-mono">{r.formula}</code>
                      {r.description && <p className="text-xs text-slate-400 mb-2.5">{r.description}</p>}
                      <div className="flex flex-wrap gap-1 mb-3">
                        {(r.linked_entities || []).map((le: string) => (
                          <span key={le} className="bg-slate-100 text-slate-500 px-2 py-0.5 rounded-lg text-[11px]">{le}</span>
                        ))}
                      </div>
                      <div className="flex gap-2">
                        <button onClick={() => handleApproveRule(r)} disabled={approving === r.name_cn}
                          className="flex items-center gap-1 px-3 py-1.5 bg-green-500 text-white rounded-lg text-xs font-medium hover:bg-green-600 disabled:opacity-50 transition-colors">
                          {approving === r.name_cn ? <Loader2 size={10} className="animate-spin" /> : <Check size={11} />}
                          采纳
                        </button>
                        <button
                          onClick={() => setSuggestions(prev => prev ? { ...prev, suggested_rules: prev.suggested_rules.filter((x: any) => x.name_cn !== r.name_cn) } : null)}
                          className="flex items-center gap-1 px-3 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-500 hover:bg-slate-50 transition-colors">
                          <X size={11} /> 忽略
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {suggestions.suggested_actions?.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-amber-700 mb-3 uppercase tracking-wide">新增动作</h4>
                <div className="space-y-3">
                  {suggestions.suggested_actions.map((a: any, i: number) => (
                    <div key={i} className="bg-white rounded-xl border border-amber-100 p-3.5 shadow-sm">
                      <div className="font-semibold text-amber-800 text-sm mb-1.5">{a.name_cn}</div>
                      <code className="block text-xs text-slate-500 bg-slate-50 rounded-lg p-2 mb-2 font-mono">{a.execution_rule}</code>
                      {a.description && <p className="text-xs text-slate-400 mb-2.5">{a.description}</p>}
                      <div className="flex gap-2">
                        <button onClick={() => handleApproveAction(a)} disabled={approving === a.name_cn}
                          className="flex items-center gap-1 px-3 py-1.5 bg-green-500 text-white rounded-lg text-xs font-medium hover:bg-green-600 disabled:opacity-50 transition-colors">
                          {approving === a.name_cn ? <Loader2 size={10} className="animate-spin" /> : <Check size={11} />}
                          采纳
                        </button>
                        <button
                          onClick={() => setSuggestions(prev => prev ? { ...prev, suggested_actions: prev.suggested_actions.filter((x: any) => x.name_cn !== a.name_cn) } : null)}
                          className="flex items-center gap-1 px-3 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-500 hover:bg-slate-50 transition-colors">
                          <X size={11} /> 忽略
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
