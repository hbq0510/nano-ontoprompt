import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { useParams, useSearchParams, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, Pause, RotateCcw, SkipForward, Clock, Users, Link2, ArrowLeft, Eye, Target, Crosshair, Radio, ChevronUp, ChevronDown, Send, Loader2, Check, X } from 'lucide-react'
import simulationApi from '@/api/v2/simulation'
import plansApi from '@/api/v2/plans'
import { ontologyApi } from '@/api/ontologies'
import SimulationMap, { type MapEntity, type MapLink } from '@/components/SimulationMap'
import type { Scenario } from '@/api/v2/simulation'
import type { ObjectInstance } from '@/types/ontology'

const STOP_LABELS: Record<string, string> = {
  max_ticks: '到达最大Tick', intercept_success: '拦截成功',
  intercept_fail: '拦截失败', target_lost: '目标丢失',
}

function isKeyEvent(e: any): boolean {
  if (e.event_type === 'stop_condition' || e.event_type === 'action_exec') return true
  if (e.event_type === 'state_change') return false
  if (e.event_type === 'rule_check') {
    const d = (e.description || '')
    if (d.includes('探测到') || d.includes('拦截') || d.includes('摧毁') || d.includes('命中')) return true
    return false
  }
  return false
}

export default function SimulationRunPage() {
  const { scenarioId } = useParams<{ scenarioId: string }>()
  const [searchParams] = useSearchParams()
  const ontologyId = searchParams.get('ontologyId') || ''
  const planId = searchParams.get('planId') || ''
  const qc = useQueryClient()
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [autoRun, setAutoRun] = useState(false)
  const [error, setError] = useState('')
  const [expandedTick, setExpandedTick] = useState<number | null>(null)
  const [viewTick, setViewTick] = useState<number | null>(null) // 当前查看的 tick（用于时间线拖拽回看）

  const { data: scenario } = useQuery({
    queryKey: ['scenario', ontologyId, scenarioId],
    queryFn: () => simulationApi.getScenario(ontologyId, scenarioId!) as Promise<Scenario>,
    enabled: !!ontologyId && !!scenarioId, refetchInterval: 3000,
  })
  const { data: instances = [] } = useQuery({
    queryKey: ['object-instances', ontologyId],
    queryFn: () => ontologyApi.listInstances(ontologyId) as Promise<ObjectInstance[]>,
    enabled: !!ontologyId,
  })
  const { data: events = [] } = useQuery({
    queryKey: ['sim-events', ontologyId, scenarioId],
    queryFn: () => simulationApi.getEvents(ontologyId, scenarioId!) as Promise<any[]>,
    enabled: !!ontologyId && !!scenarioId, refetchInterval: 2000,
  })
  const { data: timeline = [] } = useQuery({
    queryKey: ['timeline', ontologyId, scenarioId],
    queryFn: () => simulationApi.getTimeline(ontologyId, scenarioId!) as Promise<any[]>,
    enabled: !!ontologyId && !!scenarioId, refetchInterval: 2000,
  })
  const { data: planData } = useQuery({
    queryKey: ['plan', scenarioId, planId],
    queryFn: () => plansApi.get(scenarioId!, planId!).catch(() => null),
    enabled: !!scenarioId && !!planId,
  })
  const planName = (planData as any)?.name || ''
  const planScore = (planData as any)?.score

  const instanceMap = useMemo(() => {
    const m: Record<string, ObjectInstance> = {}
    ;(instances as ObjectInstance[]).forEach(i => { m[i.id] = i })
    return m
  }, [instances])

  const participantIds = scenario?.participant_instance_ids || []
  const hasStarted = scenario?.status !== 'draft'
  const currentTick = scenario?.current_tick ?? 0

  // Use viewTick if set, otherwise use latest
  const activeTickData = useMemo(() => {
    if (viewTick !== null) return timeline.find((t: any) => t.tick === viewTick) || null
    return timeline.length > 0 ? timeline[timeline.length - 1] : null
  }, [timeline, viewTick])

  // Filter events to show only those for the viewed tick
  const visibleEvents = useMemo(() => {
    const tickToShow = viewTick !== null ? viewTick : currentTick
    return (events as any[]).filter((e: any) => e.tick === tickToShow)
  }, [events, viewTick, currentTick])

  const keyEvents = useMemo(() => (events as any[]).filter(isKeyEvent), [events])

  // Map data from active tick
  const mapEntities = useMemo(() => {
    if (!activeTickData) {
      return participantIds.map(id => {
        const inst = instanceMap[id]
        if (!inst) return null
        const p = inst.properties || {}
        return { id, name: inst.name_cn, lat: +(p.latitude || 0), lon: +(p.longitude || 0) } as MapEntity
      }).filter(Boolean) as MapEntity[]
    }
    return (activeTickData.instance_states || []).map((s: any) => ({
      id: s.instance_id,
      name: s.instance_name,
      lat: +(s.properties?.latitude || instanceMap[s.instance_id]?.properties?.latitude || 0),
      lon: +(s.properties?.longitude || instanceMap[s.instance_id]?.properties?.longitude || 0),
    }))
  }, [activeTickData, participantIds, instanceMap])

  const mapLinks = useMemo(() => {
    const links = activeTickData?.active_links || []
    return links.map((l: any) => {
      const src = mapEntities.find(e => e.id === l.source_instance_id)
      const tgt = mapEntities.find(e => e.id === l.target_instance_id)
      return {
        id: l.link_id,
        sourceName: src?.name || l.source_instance_id?.slice(0, 8),
        targetName: tgt?.name || l.target_instance_id?.slice(0, 8),
        sourceLat: src?.lat || 0, sourceLon: src?.lon || 0,
        targetLat: tgt?.lat || 0, targetLon: tgt?.lon || 0,
        linkTypeId: l.link_type_id,
      } as MapLink
    })
  }, [activeTickData, mapEntities])

  // Trail: all positions of the missile across ticks
  const missileTrail = useMemo(() => {
    const trail: [number, number][] = []
    timeline.forEach((t: any) => {
      const ms = (t.instance_states || []).find((s: any) => s.instance_name?.includes('导弹') || s.instance_name?.includes('26B'))
      if (ms) trail.push([+(ms.properties?.latitude || 0), +(ms.properties?.longitude || 0)])
    })
    return trail
  }, [timeline])

  const step = useCallback(async () => {
    if (!ontologyId || !scenarioId) return; setError('')
    try {
      const r = await simulationApi.stepSimulation(ontologyId, scenarioId)
      qc.invalidateQueries({ queryKey: ['timeline', ontologyId, scenarioId] })
      qc.invalidateQueries({ queryKey: ['sim-events', ontologyId, scenarioId] })
      qc.invalidateQueries({ queryKey: ['scenario', ontologyId, scenarioId] })
      if (r.finished) { setAutoRun(false); setViewTick(null) }
    } catch (e: any) { setError(e?.response?.data?.detail || e?.message || '失败'); setAutoRun(false) }
  }, [ontologyId, scenarioId, qc])

  useEffect(() => {
    if (autoRun && (scenario?.status === 'running' || scenario?.status === 'paused')) {
      timerRef.current = setInterval(step, 1000)
    } else {
      if (timerRef.current) clearInterval(timerRef.current)
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [autoRun, scenario?.status, step])

  const handleStart = async () => { if (!ontologyId || !scenarioId) return; setError(''); setViewTick(null)
    try { await simulationApi.startSimulation(ontologyId, scenarioId); qc.invalidateQueries({ queryKey: ['scenario', ontologyId, scenarioId] }); qc.invalidateQueries({ queryKey: ['timeline', ontologyId, scenarioId] }); qc.invalidateQueries({ queryKey: ['sim-events', ontologyId, scenarioId] }) } catch (e: any) { setError(e?.response?.data?.detail || e?.message || '启动失败') } }
  const handlePause = async () => { setAutoRun(false); await simulationApi.pauseSimulation(ontologyId, scenarioId); qc.invalidateQueries({ queryKey: ['scenario', ontologyId, scenarioId] }) }
  const handleResume = async () => { setError('')
    try { await simulationApi.resumeSimulation(ontologyId, scenarioId); qc.invalidateQueries({ queryKey: ['scenario', ontologyId, scenarioId] }) } catch (e: any) { setError(e?.response?.data?.detail || e?.message || '继续失败') } }
  const handleReset = async () => { setAutoRun(false); setError(''); setExpandedTick(null); setViewTick(null)
    await simulationApi.resetSimulation(ontologyId, scenarioId); qc.invalidateQueries({ queryKey: ['scenario', ontologyId, scenarioId] }); qc.invalidateQueries({ queryKey: ['timeline', ontologyId, scenarioId] }); qc.invalidateQueries({ queryKey: ['sim-events', ontologyId, scenarioId] }) }

  const stopLabel = STOP_LABELS[(scenario as any)?.stop_condition || 'max_ticks'] || '到达最大Tick'

  return (
    <div className="h-full flex flex-col p-3 space-y-2" style={{ maxHeight: 'calc(100vh - 60px)' }}>
      {/* 顶部控制栏 */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Link to={`/ontologies/${ontologyId}?tab=simulation`} className="text-xs text-gray-400 hover:text-gray-600 shrink-0">
            <ArrowLeft size={14} />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold truncate">
                {planName ? <span className="text-purple-600">{planName}</span> : (scenario?.name || '加载...')}
                {planName && <span className="text-gray-400 font-normal"> @ {scenario?.name}</span>}
              </h2>
              {planScore && (
                <div className="text-xs text-gray-500 flex gap-2">
                  <span>杀伤{((planScore.kill_probability || 0) * 100).toFixed(0)}%</span>
                  <span>弹药{planScore.ammo_used || 0}发</span>
                  <span>用时{planScore.time_ticks || 0}tick</span>
                </div>
              )}
              <span className={`text-xs px-1.5 py-0.5 rounded whitespace-nowrap ${
                scenario?.status === 'running' ? 'bg-green-100 text-green-700' :
                scenario?.status === 'finished' ? 'bg-red-100 text-red-700' :
                scenario?.status === 'paused' ? 'bg-yellow-100 text-yellow-700' : 'bg-gray-100 text-gray-600'
              }`}>{scenario?.status === 'draft' ? '草稿' : scenario?.status === 'running' ? '运行中' : scenario?.status === 'paused' ? '暂停' : '结束'}</span>
            </div>
            <div className="text-xs text-gray-400 flex items-center gap-2">
              <Target size={11} /> {stopLabel}
              <span className="font-mono">Tick {viewTick ?? currentTick}/{scenario?.max_ticks || 50}</span>
              {viewTick !== null && viewTick !== currentTick && (
                <button onClick={() => setViewTick(null)} className="text-blue-500 underline">回到最新</button>
              )}
            </div>
          </div>
          {error && <div className="text-red-500 text-xs">{error}</div>}
        </div>
        <div className="flex gap-1.5 flex-shrink-0">
          {scenario?.status === 'draft' && (
            <button onClick={handleStart} className="btn-sm bg-green-600 text-white rounded-lg px-3 py-1.5 text-sm font-medium flex items-center gap-1"><Play size={14} />开始</button>
          )}
          {(scenario?.status === 'running' || scenario?.status === 'paused') && (
            <>
              <button onClick={step} className="btn-sm bg-blue-600 text-white rounded-lg px-3 py-1.5 text-sm font-medium flex items-center gap-1"><SkipForward size={14} />步进</button>
              <button onClick={() => setAutoRun(!autoRun)} className={`btn-sm rounded-lg px-2.5 py-1.5 text-sm font-medium flex items-center gap-1 ${autoRun ? 'bg-orange-600 text-white' : 'bg-gray-100 text-gray-700'}`}><Clock size={14} />{autoRun ? '停' : '自动'}</button>
              {scenario?.status === 'running' ? (
                <button onClick={handlePause} className="btn-sm bg-yellow-600 text-white rounded-lg px-2.5 py-1.5"><Pause size={14} /></button>
              ) : (
                <button onClick={handleResume} className="btn-sm bg-green-600 text-white rounded-lg px-2.5 py-1.5"><Play size={14} /></button>
              )}
            </>
          )}
          {(scenario?.status !== 'draft') && (
            <button onClick={handleReset} className="btn-sm border rounded-lg px-2.5 py-1.5 text-gray-600 hover:bg-gray-100"><RotateCcw size={14} /></button>
          )}
        </div>
      </div>

      {/* Tick 进度条 */}
      {hasStarted && (
        <div className="flex items-center gap-2 flex-shrink-0 px-1">
          <span className="text-[10px] text-gray-400">Tick</span>
          <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${Math.min(100, ((viewTick ?? currentTick) / (scenario?.max_ticks || 50)) * 100)}%` }} />
          </div>
          <span className="text-[10px] font-mono">{viewTick ?? currentTick}/{scenario?.max_ticks || 50}</span>
        </div>
      )}

      {/* 主体: 左 中(地图) 右 */}
      <div className="flex-1 flex gap-2 min-h-0">
        {/* 左侧面板 */}
        <div className="w-52 flex-shrink-0 flex flex-col gap-2 min-h-0">
          {/* 参与实体 */}
          <div className="border rounded-lg flex flex-col overflow-hidden" style={{ maxHeight: '40%' }}>
            <h3 className="text-[11px] font-semibold text-gray-500 uppercase p-2 pb-1 flex items-center gap-1 bg-white border-b sticky top-0 z-10"><Users size={12} />实体</h3>
            <div className="overflow-y-auto p-2 pt-1 space-y-1">
              {participantIds.map(id => {
                const inst = instanceMap[id]; if (!inst) return null
                const activeState = activeTickData?.instance_states?.find((s: any) => s.instance_id === id)
                const props = activeState?.properties || inst.properties || {}
                const keyProps = Object.entries(props).filter(([k]) => ['latitude','longitude','speed_mach','status','detect_range_km','range_km'].includes(k))
                return (
                  <div key={id} className="border rounded p-1.5 text-[11px]">
                    <div className="font-medium truncate">
                      {inst.name_cn.includes('导弹') ? '🚀' : inst.name_cn.includes('雷达') ? '📡' : '🛡️'} {inst.name_cn}
                    </div>
                    {hasStarted && keyProps.length > 0 && keyProps.map(([k,v]) => (
                      <div key={k} className="flex justify-between text-[10px]"><span className="text-gray-400">{k}</span><span className="font-mono">{typeof v === 'number' ? v.toFixed(1) : String(v)}</span></div>
                    ))}
                  </div>
                )
              })}
            </div>
          </div>
          {/* 关键事件 */}
          <div className="border rounded-lg flex flex-col overflow-hidden flex-1">
            <h3 className="text-[11px] font-semibold text-gray-500 uppercase p-2 pb-1 flex items-center gap-1 bg-white border-b sticky top-0 z-10"><Eye size={12} />事件</h3>
            <div className="overflow-y-auto p-2 pt-1">
            {!hasStarted && <div className="text-gray-400 text-[11px] text-center py-4">点击开始推演</div>}
            {hasStarted && keyEvents.length === 0 && <div className="text-gray-400 text-[11px] text-center py-4">暂无</div>}
            <div className="space-y-1">
              {keyEvents.map((e: any, i: number) => {
                const isSelected = viewTick !== null && e.tick === viewTick
                const colors: Record<string, string> = { state_change: '#f59e0b', action_exec: '#8b5cf6', rule_check: '#3b82f6', stop_condition: '#dc2626' }
                const icons: Record<string, string> = { state_change: '📊', action_exec: '⚡', rule_check: '🔍', stop_condition: '🛑' }
                return (
                  <div key={i} onClick={() => setViewTick(viewTick === e.tick ? null : e.tick)}
                    className={`text-[11px] leading-relaxed cursor-pointer px-1.5 py-0.5 rounded border-l-2 hover:bg-gray-50 ${isSelected ? 'bg-blue-50 border-l-blue-400' : ''}`}
                    style={{ borderLeftColor: colors[e.event_type] || '#999' }}>
                    <span className="font-mono text-[10px] mr-1" style={{ color: colors[e.event_type] }}>T{e.tick}</span>
                    <span>{icons[e.event_type] || '·'} </span>
                    <span>{e.description?.slice(0, 50)}</span>
                  </div>
                )
              })}
            </div>
          </div>
          </div>
        </div>

        {/* 中间：地图 */}
        <div className="flex-1 min-w-0 border rounded-lg overflow-hidden">
          <SimulationMap entities={mapEntities} links={mapLinks} trail={missileTrail} />
        </div>

        {/* 右侧：活跃关系 */}
        <div className="w-48 flex-shrink-0 border rounded-lg p-2 overflow-y-auto">
          <h3 className="text-[11px] font-semibold text-gray-500 uppercase mb-1.5 flex items-center gap-1"><Link2 size={12} />活跃关系</h3>
          {mapLinks.length === 0 ? (
            <div className="text-gray-400 text-[11px] text-center py-4">{hasStarted ? '暂无' : '开始后显示'}</div>
          ) : (
            <div className="space-y-1.5">
              {mapLinks.map((l, i) => {
                const isDetect = (l.linkTypeId || '').toLowerCase().includes('detect') || (l.linkTypeId || '').includes('探测')
                const isIntercept = (l.linkTypeId || '').toLowerCase().includes('intercept') || (l.linkTypeId || '').includes('拦截')
                return (
                  <div key={i} className="border rounded p-1.5 text-[11px]">
                    <div className={`font-medium ${isDetect ? 'text-blue-600' : isIntercept ? 'text-red-600' : 'text-gray-600'}`}>
                      {isDetect ? '📡 探测' : isIntercept ? '🛡️ 拦截' : '🔗 关系'}
                    </div>
                    <div className="flex items-center gap-1 text-[10px] text-gray-500 mt-0.5">
                      <span className="truncate max-w-[60px]">{l.sourceName}</span>
                      <span>→</span>
                      <span className="truncate max-w-[60px]">{l.targetName}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* 底部：时间线 */}
      {hasStarted && (
        <div className="h-10 border rounded-lg flex-shrink-0 overflow-x-auto p-1.5 flex items-center">
          <div className="flex gap-1 items-center h-full">
            {Array.from({ length: currentTick + 1 }, (_, i) => i).map(tick => {
              const hasKey = keyEvents.some((e: any) => e.tick === tick)
              const hasStop = keyEvents.some((e: any) => e.tick === tick && e.event_type === 'stop_condition')
              const isActive = (viewTick ?? currentTick) === tick
              return (
                <div key={tick} onClick={() => setViewTick(isActive ? null : tick)}
                  className={`flex-shrink-0 w-7 h-7 border rounded flex items-center justify-center text-[10px] cursor-pointer transition-colors relative ${
                    isActive ? 'border-blue-500 bg-blue-100 font-bold text-blue-700 ring-1 ring-blue-300' :
                    hasStop ? 'border-red-300 bg-red-50 text-red-600' :
                    hasKey ? 'border-amber-300 bg-amber-50 text-amber-700' :
                    'text-gray-400 hover:bg-gray-50'
                  }`} title={`Tick ${tick}${hasKey ? ' (关键事件)' : ''}`}>
                  {tick}
                  {hasKey && !isActive && <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full" style={{ background: hasStop ? '#dc2626' : '#f59e0b' }} />}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* 情报面板 */}
      <IntelPanel
        scenarioId={scenarioId!}
        ontologyId={ontologyId}
        planId={planId}
        currentTick={currentTick}
        hasStarted={hasStarted}
        onRefresh={() => { qc.invalidateQueries({ queryKey: ['sim-events', ontologyId, scenarioId] }); qc.invalidateQueries({ queryKey: ['timeline', ontologyId, scenarioId] }) }}
      />
    </div>
  )
}

function IntelPanel({ scenarioId, ontologyId, planId, currentTick, hasStarted, onRefresh }: {
  scenarioId: string; ontologyId: string; planId: string; currentTick: number; hasStarted: boolean; onRefresh: () => void
}) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [tick, setTick] = useState(0)
  const [parsingId, setParsingId] = useState<string | null>(null)
  const [reloading, setReloading] = useState(false)
  const qc = useQueryClient()

  const { data: intelList = [] } = useQuery({
    queryKey: ['intelligence', scenarioId, planId],
    queryFn: () => plansApi.listIntel(scenarioId, planId) as Promise<any[]>,
    enabled: !!scenarioId, refetchInterval: 5000,
  })

  const handleAdd = async () => {
    if (!text.trim()) return
    await plansApi.createIntel(scenarioId, { tick: tick || currentTick, text: text.trim(), plan_id: planId || undefined })
    setText(''); setTick(0)
    qc.invalidateQueries({ queryKey: ['intelligence', scenarioId, planId] })
  }

  const handleParse = async (id: string) => {
    setParsingId(id)
    await plansApi.parseIntel(scenarioId, id)
    setParsingId(null)
    qc.invalidateQueries({ queryKey: ['intelligence', scenarioId, planId] })
  }

  const handleApply = async (id: string) => {
    setApplyingId(id)
    await plansApi.applyIntel(scenarioId, id)
    setApplyingId(null)
    qc.invalidateQueries({ queryKey: ['intelligence', scenarioId, planId] })
    onRefresh()
  }

  const handleDelete = async (id: string) => {
    await plansApi.deleteIntel(scenarioId, id)
    qc.invalidateQueries({ queryKey: ['intelligence', scenarioId, planId] })
  }

  const pending = intelList.filter((i: any) => i.status === 'pending')
  const parsed = intelList.filter((i: any) => i.status === 'ready')
  const applied = intelList.filter((i: any) => i.status === 'applied')

  return (
    <div className="border rounded-lg flex-shrink-0">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between p-2 hover:bg-gray-50">
        <span className="text-xs font-semibold text-gray-500 uppercase flex items-center gap-1">
          <Radio size={12} className={pending.length > 0 ? 'text-red-500 animate-pulse' : ''} /> 情报输入
          {pending.length > 0 && <span className="bg-red-500 text-white text-[10px] px-1 rounded">{pending.length}</span>}
        </span>
        {open ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
      </button>
      {open && (
        <div className="border-t p-2 space-y-2">
          {/* Input */}
          <div className="flex gap-1">
            <input type="number" value={tick || currentTick} onChange={e => setTick(+e.target.value)}
              placeholder="Tick" className="w-14 border rounded px-1.5 py-1 text-xs" />
            <input value={text} onChange={e => setText(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAdd()}
              placeholder="输入情报文本，如: 雷达被诱饵干扰, 丢失对T1的锁定"
              className="flex-1 border rounded px-2 py-1 text-xs" />
            <button onClick={handleAdd} disabled={!text.trim()}
              className="px-2 py-1 bg-indigo-600 text-white rounded text-xs disabled:opacity-50 flex items-center gap-1"><Send size={10} />添加</button>
          </div>
          {/* Intel list */}
          <div className="max-h-40 overflow-y-auto space-y-1">
            {intelList.length === 0 && <div className="text-xs text-gray-400 text-center py-2">暂无情报，可在推演中插入</div>}
            {intelList.map((it: any) => (
              <div key={it.id} className={`flex items-start justify-between text-xs p-1.5 rounded ${it.status === 'applied' ? 'bg-green-50' : it.status === 'ready' ? 'bg-blue-50' : 'bg-gray-50'}`}>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1">
                    <span className="font-mono text-[10px] text-gray-400">T{it.tick}</span>
                    <span className={`text-[10px] px-1 rounded ${it.status === 'applied' ? 'bg-green-200 text-green-700' : it.status === 'ready' ? 'bg-blue-200 text-blue-700' : 'bg-gray-200 text-gray-600'}`}>
                      {it.status === 'applied' ? '已应用' : it.status === 'ready' ? '就绪' : '待处理'}
                    </span>
                  </div>
                  <div className="text-gray-600 truncate mt-0.5">{it.text}</div>
                  {it.parsed && <div className="text-[10px] text-gray-400 mt-0.5">{it.parsed.length} 个操作</div>}
                </div>
                <div className="flex gap-0.5 ml-1 flex-shrink-0">
                  {it.status === 'pending' && (
                    <button onClick={() => handleParse(it.id)} disabled={parsingId === it.id}
                      className="px-1.5 py-0.5 bg-blue-500 text-white rounded text-[10px] flex items-center gap-0.5">
                      {parsingId === it.id ? <Loader2 size={10} className="animate-spin" /> : null}🤖
                    </button>
                  )}
                  {it.status === 'ready' && (
                    <button onClick={() => handleApply(it.id)} disabled={applyingId === it.id}
                      className="px-1.5 py-0.5 bg-green-500 text-white rounded text-[10px] flex items-center gap-0.5">
                      {applyingId === it.id ? <Loader2 size={10} className="animate-spin" /> : null}✓
                    </button>
                  )}
                  <button onClick={() => handleDelete(it.id)} className="px-1 py-0.5 text-red-400 hover:bg-red-50 rounded text-[10px]">✕</button>
                </div>
              </div>
            ))}
          </div>
          {/* Preset templates */}
          <div className="flex gap-1 flex-wrap">
            <span className="text-[10px] text-gray-400">模板:</span>
            {[
              '雷达被诱饵干扰,丢失对目标的锁定',
              '拦截弹弹药不足,仅剩1发',
              '发现新目标! 导弹B从东面接近',
              '雷达信号恢复,重新锁定目标',
            ].map(tpl => (
              <button key={tpl} onClick={() => setText(tpl)}
                className="text-[10px] px-1.5 py-0.5 border rounded hover:bg-gray-100 text-gray-500 whitespace-nowrap">{tpl.slice(0,12)}...</button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
