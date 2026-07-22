import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Plus, Trash2, Play, Eye, Target, Zap, BarChart3, Sparkles, Lightbulb, Check, X,
  ChevronDown, ChevronRight, ChevronUp, AlertTriangle, RotateCcw, Trophy, Save, BookOpen, MonitorPlay,
  Radio, Send, Loader2
} from 'lucide-react'
import plansApi from '@/api/v2/plans'
import simulationApi from '@/api/v2/simulation'
import type { PlanData } from '@/api/v2/plans'

const SCORE_LABELS: Record<string, string> = {
  kill_probability: '杀伤概率', ammo_used: '弹药消耗', time_ticks: '用时(tick)',
  efficiency: '效率分', decisions_executed: '决策步数',
}

export default function PlansPanel({ ontologyId, scenarioId, scenarioName }: { ontologyId: string; scenarioId: string; scenarioName: string }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [generating, setGenerating] = useState(false)
  const [expandedPlan, setExpandedPlan] = useState<string | null>(null)
  const [genCount, setGenCount] = useState(3)
  const [genStrategy, setGenStrategy] = useState('diverse')

  const { data: plans = [] } = useQuery({
    queryKey: ['plans', scenarioId],
    queryFn: () => plansApi.list(scenarioId) as Promise<PlanData[]>,
    enabled: !!scenarioId, refetchInterval: 5000,
  })

  const { data: compare } = useQuery({
    queryKey: ['plans-compare', scenarioId],
    queryFn: () => plansApi.compare(scenarioId),
    enabled: !!scenarioId,
  })

  const deleteMut = useMutation({ mutationFn: (id: string) => plansApi.delete(scenarioId, id), onSuccess: () => qc.invalidateQueries({ queryKey: ['plans', scenarioId] }) })
  const runMut = useMutation({
    mutationFn: (id: string) => plansApi.run(scenarioId, id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['plans', scenarioId] }); qc.invalidateQueries({ queryKey: ['plans-compare', scenarioId] }) },
  })
  const saveTplMut = useMutation({ mutationFn: (id: string) => plansApi.saveTemplate(scenarioId, id), onSuccess: () => qc.invalidateQueries({ queryKey: ['plans', scenarioId] }) })

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      await plansApi.generate(scenarioId, genCount, genStrategy)
      qc.invalidateQueries({ queryKey: ['plans', scenarioId] })
    } catch (e: any) { alert('生成失败: ' + (e?.message || e)) }
    finally { setGenerating(false) }
  }

  const best = (compare as any)?.best
  const evaluated = plans.filter((p: PlanData) => p.status === 'evaluated')

  return (
    <div className="space-y-4">
      {/* 顶部操作栏 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">任务中心 · {scenarioName}</h2>
          <p className="text-sm text-gray-500">智能方案生成 · 仿真评估 · 对比择优</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => navigate(`/simulation/${scenarioId}?ontologyId=${ontologyId}`)}
            className="inline-flex items-center gap-1 px-3 py-1.5 border text-sm rounded-lg hover:bg-gray-100">
            <Eye size={14} /> 仿真视图
          </button>
        </div>
      </div>

      {/* LLM 方案生成 */}
      <div className="border rounded-lg p-4 bg-gradient-to-r from-indigo-50 to-blue-50">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles size={18} className="text-indigo-500" />
          <h3 className="font-semibold">智能方案生成</h3>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-sm text-gray-600">生成</span>
          <select value={genCount} onChange={e => setGenCount(+e.target.value)} className="border rounded px-2 py-1 text-sm">
            {[1,2,3,4,5].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
          <span className="text-sm text-gray-600">个方案, 策略:</span>
          <select value={genStrategy} onChange={e => setGenStrategy(e.target.value)} className="border rounded px-2 py-1 text-sm">
            <option value="diverse">多样化</option>
            <option value="conservative">保守</option>
            <option value="aggressive">激进</option>
          </select>
          <button onClick={handleGenerate} disabled={generating}
            className="inline-flex items-center gap-1 px-4 py-1.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 disabled:opacity-50">
            {generating ? <><RotateCcw size={14} className="animate-spin" /> 生成中...</> : <><Sparkles size={14} /> 生成方案</>}
          </button>
        </div>
      </div>

      {/* 情报输入区 */}
      <IntelSection scenarioId={scenarioId} />

      {/* 方案对比 (雷达图效果的简化版) */}
      {evaluated.length >= 2 && (
        <div className="border rounded-lg p-4 bg-amber-50/50">
          <h3 className="font-semibold text-sm mb-2 flex items-center gap-1"><Trophy size={16} className="text-amber-500" /> 方案对比</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-1 font-medium">方案</th>
                  <th className="pb-1 font-medium">杀伤概率</th>
                  <th className="pb-1 font-medium">弹药消耗</th>
                  <th className="pb-1 font-medium">用时</th>
                  <th className="pb-1 font-medium">效率</th>
                  <th className="pb-1 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {evaluated.map((p: PlanData) => {
                  const s = p.score || {}
                  const isBest = best?.plan_id === p.id
                  return (
                    <tr key={p.id} className={`border-b ${isBest ? 'bg-amber-100/50 font-medium' : ''}`}>
                      <td className="py-1.5">{isBest && '🏆 '}{p.name}</td>
                      <td className="py-1.5">{(s.kill_probability || 0) * 100}%</td>
                      <td className="py-1.5">{s.ammo_used || 0}枚</td>
                      <td className="py-1.5">{s.time_ticks || 0}tick</td>
                      <td className="py-1.5">{s.efficiency || 0}</td>
                      <td className="py-1.5">
                        <button onClick={() => saveTplMut.mutate(p.id)} className="text-xs text-blue-500 hover:underline flex items-center gap-0.5"><Save size={10} />存模板</button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 方案列表 */}
      {plans.length === 0 ? (
        <div className="text-center text-gray-400 py-8">
          <Lightbulb size={32} className="mx-auto mb-2 opacity-30" />
          <p>暂无方案，点击上方"生成方案"或手动创建</p>
        </div>
      ) : (
        <div className="space-y-2">
          {plans.map((p: PlanData) => {
            const expanded = expandedPlan === p.id
            return (
              <div key={p.id} className="border rounded-lg overflow-hidden">
                <div className="flex items-center justify-between p-3 hover:bg-gray-50 cursor-pointer"
                  onClick={() => setExpandedPlan(expanded ? null : p.id)}>
                  <div className="flex items-center gap-3">
                    <span>{expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</span>
                    <div>
                      <span className="font-medium">{p.name}</span>
                      <span className={`ml-2 text-xs px-1.5 py-0.5 rounded ${
                        p.status === 'evaluated' ? 'bg-green-100 text-green-700' :
                        p.status === 'running' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600'
                      }`}>{p.status === 'evaluated' ? '已评估' : p.status === 'running' ? '运行中' : '待执行'}</span>
                      <span className="ml-2 text-xs text-gray-400">{(p.decisions||[]).length}步决策</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
                    {p.status !== 'evaluated' && (
                      <button onClick={() => runMut.mutate(p.id)} className="p-1.5 text-green-600 hover:bg-green-50 rounded" title="首次执行"><Play size={14} /></button>
                    )}
                    {p.status === 'evaluated' && (
                      <>
                        <button onClick={() => { runMut.mutate(p.id); qc.invalidateQueries({ queryKey: ['intel-plans', scenarioId] }) }}
                          className="p-1.5 text-orange-600 hover:bg-orange-50 rounded" title="重新执行"><RotateCcw size={14} /></button>
                        <button onClick={() => navigate(`/simulation/${scenarioId}?ontologyId=${ontologyId}&planId=${p.id}`)}
                          className="p-1.5 text-purple-600 hover:bg-purple-50 rounded" title="查看推演"><MonitorPlay size={14} /></button>
                      </>
                    )}
                    <button onClick={() => { if (confirm('确定删除?')) deleteMut.mutate(p.id) }}
                      className="p-1.5 text-red-400 hover:bg-red-50 rounded"><Trash2 size={14} /></button>
                  </div>
                </div>
                {expanded && (
                  <div className="border-t p-3 bg-gray-50/50 space-y-2 text-sm">
                    {p.description && <p className="text-gray-500">{p.description}</p>}
                    <div className="font-medium text-xs text-gray-400 uppercase">决策链</div>
                    <div className="space-y-1">
                      {(p.decisions || []).map((d, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs ml-2">
                          <span className="w-5 h-5 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-[10px] font-bold">{i+1}</span>
                          <span className="text-gray-600">WHEN</span>
                          <code className="bg-white px-1.5 py-0.5 rounded border text-[11px]">{d.trigger}</code>
                          <span className="text-gray-400">→</span>
                          <span className="font-medium">{d.action}</span>
                          {d.target && <span className="text-gray-400">[{d.target}]</span>}
                          {d.params && Object.keys(d.params).length > 0 && (
                            <span className="text-gray-400 text-[10px]">{JSON.stringify(d.params)}</span>
                          )}
                        </div>
                      ))}
                    </div>
                    {p.score && Object.keys(p.score).length > 0 && (
                      <div>
                        <div className="font-medium text-xs text-gray-400 uppercase mt-2">评估结果</div>
                        <div className="flex gap-3 mt-1">
                          {Object.entries(p.score).map(([k, v]) => (
                            <span key={k} className="text-xs bg-white border rounded px-2 py-0.5">
                              {SCORE_LABELS[k] || k}: <strong>{typeof v === 'number' ? v.toFixed(2) : String(v)}</strong>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* 模板库入口 */}
      <div className="border-t pt-3">
        <button onClick={() => {/* TODO: template library page */}} className="text-sm text-gray-500 hover:text-indigo-600 inline-flex items-center gap-1">
          <BookOpen size={14} /> 方案模板库 (经验库)
        </button>
      </div>
    </div>
  )
}

function IntelSection({ scenarioId }: { scenarioId: string }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [tick, setTick] = useState(8)
  const [parsing, setParsing] = useState(false)
  const qc = useQueryClient()

  const { data: intelList = [] } = useQuery({
    queryKey: ['intel-plans', scenarioId],
    queryFn: () => plansApi.listIntel(scenarioId) as Promise<any[]>,
    enabled: !!scenarioId, refetchInterval: 5000,
  })

  const pending = intelList.filter((i: any) => i.status === 'pending')
  const ready = intelList.filter((i: any) => i.status === 'ready')

  return (
    <div className="border rounded-lg">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between p-2.5 hover:bg-gray-50">
        <span className="text-sm font-semibold text-gray-600 flex items-center gap-1.5">
          <Radio size={14} className={pending.length > 0 ? 'text-red-500 animate-pulse' : ''} /> 情报输入
          {ready.length > 0 && <span className="bg-blue-500 text-white text-[10px] px-1.5 rounded-full">{ready.length} 就绪</span>}
        </span>
        {open ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
      </button>
      {open && (
        <div className="border-t p-2.5 space-y-2 bg-gray-50/50">
          <div className="flex gap-1.5">
            <input type="number" value={tick} onChange={e => setTick(+e.target.value)} className="w-14 border rounded px-1.5 py-1 text-xs" />
            <input value={text} onChange={e => setText(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && (setParsing(true), plansApi.createIntel(scenarioId, { tick, text: text.trim() }).then(r => plansApi.parseIntel(scenarioId, r.id).finally(() => { setParsing(false); setText(''); qc.invalidateQueries({ queryKey: ['intel-plans', scenarioId] }) })).catch(() => setParsing(false)))}
              placeholder="情报文本, 如: 发现新导弹 lat 30.5 lon 122 speed Mach5"
              className="flex-1 border rounded px-2 py-1 text-xs" />
            <button onClick={async () => {
              if (!text.trim()) return; setParsing(true)
              try { const r = await plansApi.createIntel(scenarioId, { tick, text: text.trim() }); await plansApi.parseIntel(scenarioId, r.id); setText(''); qc.invalidateQueries({ queryKey: ['intel-plans', scenarioId] }) } catch(e){}
              finally { setParsing(false) }
            }} disabled={!text.trim() || parsing}
              className="px-2 py-1 bg-indigo-600 text-white rounded text-xs disabled:opacity-50 flex items-center gap-1 whitespace-nowrap">
              {parsing ? <Loader2 size={10} className="animate-spin" /> : <Send size={10} />}添加
            </button>
          </div>
          {intelList.length > 0 && (
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {intelList.map((it: any) => (
                <div key={it.id} className={`flex items-center justify-between text-xs p-1.5 rounded ${it.status === 'applied' ? 'bg-green-100' : it.status === 'ready' ? 'bg-blue-50' : 'bg-gray-50'}`}>
                  <div className="flex-1 min-w-0">
                    <span className="font-mono text-[10px] mr-1">T{it.tick}</span>
                    <span className={`text-[10px] px-1 rounded mr-1 ${it.status === 'applied' ? 'bg-green-200' : it.status === 'ready' ? 'bg-blue-200' : 'bg-gray-200'}`}>
                      {it.status === 'applied' ? '生效' : it.status === 'ready' ? '就绪' : '待解析'}
                    </span>
                    <span className="text-gray-600 truncate">{it.text}</span>
                  </div>
                  <div className="flex gap-0.5">
                    {it.status === 'pending' && (
                      <button onClick={async () => { await plansApi.parseIntel(scenarioId, it.id); qc.invalidateQueries({ queryKey: ['intel-plans', scenarioId] }) }}
                        className="px-1 py-0.5 bg-blue-500 text-white rounded text-[10px]">🤖</button>
                    )}
                    <button onClick={async () => { await plansApi.deleteIntel(scenarioId, it.id); qc.invalidateQueries({ queryKey: ['intel-plans', scenarioId] }) }}
                      className="px-1 py-0.5 text-red-400 hover:bg-red-50 rounded text-[10px]">✕</button>
                  </div>
                </div>
              ))}
            </div>
          )}
          {ready.length > 0 && (
            <div className="text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded text-center">
              情报已就绪! 重新执行方案即可生效
            </div>
          )}
          <div className="flex gap-1 flex-wrap">
            <span className="text-[10px] text-gray-400">模板:</span>
            {['发现新导弹 lat 30.5 lon 122 speed Mach5','雷达被干扰丢失锁定','弹药不足 only 1 发'].map(t => (
              <button key={t} onClick={() => { setText(t); setTick(8) }} className="text-[10px] px-1.5 py-0.5 border rounded hover:bg-gray-100 text-gray-500 whitespace-nowrap">{t.slice(0,15)}...</button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
