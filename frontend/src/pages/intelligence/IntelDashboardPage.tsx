import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { intelApi } from '@/api/intel'
import type { IntelAssessData, IntelSnapshot } from '@/types/intel'
import { DANGER_LABELS, DANGER_COLORS } from '@/types/intel'
import { Send, Loader2, Shield, Link2, Clock, Crosshair } from 'lucide-react'
import cytoscape from 'cytoscape'

// ── Type colors (same palette as GraphTabV2) ────────────────────────
const TYPE_COLORS: Record<string, string> = {
  Organization: '#7c3aed', Facility: '#2563eb', Product: '#059669',
  Material: '#d97706', Process: '#db2777', Document: '#ea580c',
  Category: '#0891b2', Concept: '#4f46e5', Weapon: '#dc2626',
  Unit: '#e11d48',
}
const FALLBACK_COLORS = ['#2563eb','#059669','#dc2626','#7c3aed','#d97706','#0891b2','#db2777','#4f46e5','#65a30d','#be123c']

function nodeColor(labels: string[]): string {
  for (const l of labels) { if (TYPE_COLORS[l]) return TYPE_COLORS[l] }
  let hash = 0
  for (let i = 0; i < (labels[0] || 'Entity').length; i += 1) hash = ((hash << 5) - hash + (labels[0] || 'Entity').charCodeAt(i)) | 0
  return FALLBACK_COLORS[Math.abs(hash) % FALLBACK_COLORS.length]
}

// ── DangerGauge SVG component ───────────────────────────────────────
function DangerGauge({ score, level }: { score: number; level: string }) {
  const color = DANGER_COLORS[level] || '#6b7280'
  const angle = Math.min((score / 100) * 180, 180)
  const rad = (angle * Math.PI) / 180
  const r = 80
  const cx = 100; const cy = 100
  const nx = cx + r * Math.cos(Math.PI - rad)
  const ny = cy - r * Math.sin(Math.PI - rad)
  const largeArc = angle > 90 ? 1 : 0

  return (
    <div className="flex flex-col items-center">
      <svg width="200" height="120" viewBox="0 0 200 120">
        {/* Background arc */}
        <defs>
          <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#10b981" />
            <stop offset="33%" stopColor="#f59e0b" />
            <stop offset="66%" stopColor="#f97316" />
            <stop offset="100%" stopColor="#ef4444" />
          </linearGradient>
        </defs>
        <path d="M20,100 A80,80 0 0,1 180,100" fill="none" stroke="#e5e7eb" strokeWidth="20" strokeLinecap="round" />
        {/* Active arc */}
        {score > 0 && (
          <path d={`M20,100 A80,80 0 ${largeArc},1 ${nx},${ny}`} fill="none" stroke={color} strokeWidth="20" strokeLinecap="round" />
        )}
        {/* Needle */}
        <line x1={cx} y1={cy} x2={nx || 20} y2={ny || 100} stroke="#1f2937" strokeWidth="2" strokeLinecap="round" />
        <circle cx={cx} cy={cy} r="4" fill="#1f2937" />
      </svg>
      <div className="text-3xl font-bold" style={{ color }}>{score}</div>
      <div className="text-sm font-medium" style={{ color }}>{DANGER_LABELS[level] || level}</div>
    </div>
  )
}

// ── Main page ───────────────────────────────────────────────────────
export default function IntelDashboardPage() {
  const { ontologyId: urlOid } = useParams<{ ontologyId?: string }>()
  const navigate = useNavigate()
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)

  const [oid, setOid] = useState<string | null>(urlOid || null)
  const [data, setData] = useState<IntelAssessData | null>(null)
  const [intelText, setIntelText] = useState('')
  const [isExtracting, setIsExtracting] = useState(false)
  const [loading, setLoading] = useState(false)
  const [selectedSnapshot, setSelectedSnapshot] = useState<IntelSnapshot | null>(null)

  // ── Init or load ──────────────────────────────────────────────────
  useEffect(() => {
    if (oid) {
      loadAssess()
    }
  }, [oid])

  const loadAssess = async () => {
    if (!oid) return
    setLoading(true)
    try {
      const d = await intelApi.assess(oid) as IntelAssessData
      setData(d)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }

  const handleInit = async () => {
    const res = await intelApi.init({ name: '战时情报分析演示', description: '动态本体演示' }) as { ontology_id: string }
    setOid(res.ontology_id)
    navigate(`/intelligence/${res.ontology_id}`, { replace: true })
  }

  // ── Submit intel — LLM 抽取 + 轮询结果 ─────────────────────────
  const handleSubmit = async () => {
    if (!intelText.trim() || isExtracting) return
    setIsExtracting(true)
    try {
      // 1. 新建独立会话
      const initRes = await intelApi.init({ name: `情报评估-${new Date().toLocaleTimeString('zh-CN')}`, description: '单条情报独立评估' }) as { ontology_id: string }
      const newOid = initRes.ontology_id
      setOid(newOid)
      navigate(`/intelligence/${newOid}`, { replace: true })
      // 2. 提交情报 → LLM 抽取
      await intelApi.submit(newOid, intelText.trim())
      setIntelText('')
      // 3. 轮询直到抽取完成
      pollForResult(newOid)
    } catch {
      setIsExtracting(false)
    }
  }

  const pollForResult = (targetOid: string) => {
    let count = 0
    const maxPolls = 60  // 3 minutes max
    const check = async () => {
      if (count >= maxPolls) { setIsExtracting(false); return }
      count++
      try {
        const res = await intelApi.assess(targetOid) as IntelAssessData
        // 检查是否所有 snapshots 都完成了
        const allDone = res.snapshots.every(s => s.status !== 'extracting')
        if (allDone) {
          setData(res)
          setIsExtracting(false)
        } else {
          setTimeout(check, 3000)
        }
      } catch {
        setTimeout(check, 3000)
      }
    }
    check()
  }

  // ── Cytoscape graph ───────────────────────────────────────────────
  useEffect(() => {
    if (!data?.graph || !containerRef.current) return
    if (cyRef.current) { cyRef.current.destroy(); cyRef.current = null }

    const { nodes, edges } = data.graph
    if (nodes.length === 0) return

    const cy = cytoscape({
      container: containerRef.current,
      elements: [
        ...nodes.map(n => ({
          data: {
            id: n.id,
            label: n.properties?.name_cn || n.id.slice(0, 8),
            typeLabel: n.labels?.[0] || 'Entity',
          },
          style: {
            'background-color': nodeColor(n.labels || []),
            label: String(n.properties?.name_cn || n.id.slice(0, 8)),
            'font-size': '10px',
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-wrap': 'ellipsis',
            'text-max-width': '100px',
          },
        })),
        ...edges.map(e => ({
          data: {
            id: e.id,
            source: e.source,
            target: e.target,
            label: e.type,
          },
        })),
      ],
      style: [
        { selector: 'node', style: { width: 30, height: 30, 'border-width': 2, 'border-color': '#fff' } },
        { selector: 'edge', style: { width: 1.5, 'line-color': '#94a3b8', 'target-arrow-color': '#94a3b8', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'font-size': 8, 'text-background-opacity': 1, 'text-background-color': '#fff', 'text-background-padding': '2px', label: 'data(label)' } },
      ],
      layout: { name: 'cose', animate: false, nodeRepulsion: () => 4000, idealEdgeLength: () => 80 },
    })
    cyRef.current = cy
    return () => { cy.destroy(); cyRef.current = null }
  }, [data?.graph])

  // ── Empty state ───────────────────────────────────────────────────
  if (!oid) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6">
        <Crosshair size={48} className="text-gray-300" />
        <div className="text-center">
          <h2 className="text-xl font-semibold mb-2">军事动态情报分析演示</h2>
          <p className="text-gray-500 text-sm mb-6">模拟实时情报输入，观察知识图谱动态演化与威胁评估</p>
          <button onClick={handleInit} className="bg-black text-white px-6 py-3 rounded-lg text-sm">
            初始化情报分析会话
          </button>
        </div>
      </div>
    )
  }

  // ── Dashboard ─────────────────────────────────────────────────────
  return (
    <div className="h-full flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Crosshair size={20} />
          军事动态情报分析演示
          {data && <span className="text-sm text-gray-400 font-normal">— {data.ontology_name}</span>}
        </h2>
      </div>

      <div className="flex-1 flex gap-4 min-h-0">
        {/* Left: Graph + Input + Timeline */}
        <div className="flex-1 flex flex-col gap-3 min-w-0">
          {/* Intel input */}
          <div className="flex gap-2">
            <textarea
              value={intelText}
              onChange={e => setIntelText(e.target.value)}
              placeholder="输入军事情报文本...&#10;例：发现敌军坦克部队向北部防线接近，距离约30公里"
              rows={3}
              className="flex-1 border rounded-lg px-3 py-2 text-sm resize-none"
              disabled={isExtracting}
              onKeyDown={e => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleSubmit()
              }}
            />
            <button
              onClick={handleSubmit}
              disabled={!intelText.trim() || isExtracting}
              className="shrink-0 flex items-center gap-1.5 px-4 py-2 bg-black text-white rounded-lg text-sm disabled:opacity-50"
            >
              {isExtracting ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              提交
            </button>
          </div>

          {/* Graph */}
          <div className="flex-1 bg-white border rounded-lg relative min-h-[300px]">
            {!data?.graph?.nodes?.length ? (
              <div className="absolute inset-0 flex items-center justify-center text-gray-400 text-sm">
                {loading ? <Loader2 size={24} className="animate-spin" /> : '提交情报后将在此显示知识图谱'}
              </div>
            ) : null}
            <div ref={containerRef} className="absolute inset-0" />
            {data?.graph?.nodes?.length ? (
              <div className="absolute bottom-2 left-2 text-xs text-gray-400 bg-white/80 px-2 py-1 rounded">
                {data.graph.nodes.length} 节点 · {data.graph.edges.length} 边
                {data.graph.neo4j_available ? ' · Neo4j' : ' · PostgreSQL'}
              </div>
            ) : null}
          </div>

          {/* Timeline */}
          <div className="bg-white border rounded-lg p-3 max-h-[200px] overflow-y-auto">
            <h3 className="text-sm font-medium mb-2 flex items-center gap-1"><Clock size={14} /> 情报时间线</h3>
            {!data?.snapshots?.length ? (
              <p className="text-gray-400 text-xs">尚无情报数据</p>
            ) : (
              <div className="flex gap-3 overflow-x-auto pb-2">
                {data.snapshots.map(s => (
                  <button
                    key={s.id}
                    onClick={() => setSelectedSnapshot(s)}
                    className={`shrink-0 text-left p-2 rounded-lg border min-w-[120px] text-xs transition-colors ${
                      selectedSnapshot?.id === s.id ? 'border-black bg-gray-50' : 'border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-1">
                      <span className="font-semibold">{s.label}</span>
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{ backgroundColor: DANGER_COLORS[s.danger_level] || '#6b7280' }}
                      />
                    </div>
                    <div className="text-gray-500">
                      {(s.status === 'extracting') ? (
                        <span className="flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> 抽取中</span>
                      ) : (
                        <span>{DANGER_LABELS[s.danger_level] || '-'} · {s.entity_count}实体</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
            {/* Selected snapshot detail */}
            {selectedSnapshot && (
              <div className="mt-2 p-2 bg-gray-50 rounded text-xs text-gray-600 max-h-[60px] overflow-y-auto">
                {selectedSnapshot.intel_text}
              </div>
            )}
          </div>
        </div>

        {/* Right panel */}
        <div className="w-72 flex flex-col gap-3 shrink-0">
          {/* Danger Gauge */}
          <div className="bg-white border rounded-lg p-4 flex flex-col items-center">
            <DangerGauge score={data?.danger_score || 0} level={data?.danger_level || 'low'} />
          </div>

          {/* Recommendations */}
          <div className="bg-white border rounded-lg p-4 flex-1">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-1">
              <Shield size={14} /> 战术建议
            </h3>
            {!data?.recommendations?.length ? (
              <p className="text-gray-400 text-xs">暂无建议</p>
            ) : (
              <ol className="space-y-2">
                {data.recommendations.map((r, i) => (
                  <li key={i} className="text-xs flex items-start gap-2">
                    <span className="font-bold text-gray-400 shrink-0">{i + 1}.</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-white border rounded-lg p-3 text-center">
              <Shield size={16} className="mx-auto text-gray-400 mb-1" />
              <div className="text-lg font-bold">{data?.entity_count || 0}</div>
              <div className="text-[10px] text-gray-400">实体</div>
            </div>
            <div className="bg-white border rounded-lg p-3 text-center">
              <Link2 size={16} className="mx-auto text-gray-400 mb-1" />
              <div className="text-lg font-bold">{data?.relation_count || 0}</div>
              <div className="text-[10px] text-gray-400">关系</div>
            </div>
            <div className="bg-white border rounded-lg p-3 text-center">
              <Clock size={16} className="mx-auto text-gray-400 mb-1" />
              <div className="text-lg font-bold">{data?.snapshots?.length || 0}</div>
              <div className="text-[10px] text-gray-400">时间点</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
