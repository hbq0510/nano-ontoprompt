import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Play, Pause, RotateCcw, Plus, Trash2, Clock, Eye, Users, Edit3, X, Save, Zap } from 'lucide-react'
import simulationApi from '@/api/v2/simulation'
import plansApi from '@/api/v2/plans'
import { ontologyApi } from '@/api/ontologies'
import type { Scenario } from '@/api/v2/simulation'
import type { ObjectInstance } from '@/types/ontology'
import PlansPanel from './PlansPanel'

const STATUS_LABELS: Record<string, { cn: string; color: string }> = {
  draft:     { cn: '草稿',   color: 'bg-gray-200 text-gray-700' },
  running:   { cn: '运行中', color: 'bg-green-200 text-green-800' },
  paused:    { cn: '已暂停', color: 'bg-yellow-200 text-yellow-800' },
  finished:  { cn: '已结束', color: 'bg-blue-200 text-blue-800' },
}

export default function ScenarioListPage({ ontologyId }: { ontologyId: string }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<'scenarios' | 'plans'>('scenarios')
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [editSid, setEditSid] = useState<string | null>(null)
  const [form, setForm] = useState({ name: '', description: '', max_ticks: 50, tick_interval_ms: 500, stop_condition: 'max_ticks', participant_instance_ids: [] as string[] })
  const [editForm, setEditForm] = useState({ name: '', description: '', max_ticks: 50, stop_condition: 'max_ticks', participant_instance_ids: [] as string[] })

  const { data: scenarios = [], isLoading } = useQuery({
    queryKey: ['scenarios', ontologyId],
    queryFn: () => simulationApi.listScenarios(ontologyId) as Promise<Scenario[]>,
  })

  // 加载所有实例以便显示参与者名称
  const { data: instances = [] } = useQuery({
    queryKey: ['object-instances', ontologyId],
    queryFn: () => ontologyApi.listInstances(ontologyId) as Promise<ObjectInstance[]>,
  })

  const instanceMap = (instances as ObjectInstance[]).reduce((m, i) => { m[i.id] = i; return m }, {} as Record<string, ObjectInstance>)

  const createMut = useMutation({
    mutationFn: (d: any) => simulationApi.createScenario(ontologyId, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['scenarios', ontologyId] }); setShowCreate(false); setForm({ name: '', description: '', max_ticks: 50, tick_interval_ms: 500, stop_condition: 'max_ticks', participant_instance_ids: [] }) },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => simulationApi.deleteScenario(ontologyId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scenarios', ontologyId] }),
  })

  const startMut = useMutation({
    mutationFn: (id: string) => simulationApi.startSimulation(ontologyId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scenarios', ontologyId] }),
  })

  const pauseMut = useMutation({
    mutationFn: (id: string) => simulationApi.pauseSimulation(ontologyId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scenarios', ontologyId] }),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => simulationApi.updateScenario(ontologyId, id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['scenarios', ontologyId] }); setEditSid(null) },
  })

  const resetMut = useMutation({
    mutationFn: (id: string) => simulationApi.resetSimulation(ontologyId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scenarios', ontologyId] }),
  })

  if (isLoading) return <div className="p-6 text-gray-400">加载中...</div>

  // 如果选中了任务，显示方案面板
  if (activeTab === 'plans' && selectedScenario) {
    const s = (scenarios as Scenario[]).find(x => x.id === selectedScenario)
    return (
      <div>
        <button onClick={() => { setActiveTab('scenarios'); setSelectedScenario(null) }}
          className="text-sm text-gray-500 hover:text-gray-700 mb-3 inline-flex items-center gap-1">
          ← 返回想定列表
        </button>
        <PlansPanel ontologyId={ontologyId} scenarioId={selectedScenario} scenarioName={s?.name || ''} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h2 className="text-lg font-semibold">任务中心</h2>
          <div className="flex border rounded-lg overflow-hidden text-sm">
            <button onClick={() => setActiveTab('scenarios')}
              className={`px-3 py-1 ${activeTab === 'scenarios' ? 'bg-black text-white' : 'bg-white text-gray-600 hover:bg-gray-100'}`}>想定</button>
            <button onClick={() => setActiveTab('plans')}
              className={`px-3 py-1 ${activeTab === 'plans' ? 'bg-black text-white' : 'bg-white text-gray-600 hover:bg-gray-100'}`}>方案</button>
          </div>
        </div>
        <button onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700">
          <Plus size={14} /> 新建想定
        </button>
      </div>

      {/* 新建表单 */}
      {showCreate && (
        <div className="border rounded-lg p-4 bg-gray-50 space-y-3">
          <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
            placeholder="想定名称" className="w-full border rounded px-3 py-2 text-sm" />
          <textarea value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
            placeholder="描述（可选）" className="w-full border rounded px-3 py-2 text-sm" rows={2} />
          <div className="flex gap-4">
            <label className="text-sm text-gray-500">
              最大 Tick <input type="number" value={form.max_ticks}
                onChange={e => setForm(p => ({ ...p, max_ticks: +e.target.value }))}
                className="ml-1 border rounded px-2 py-1 w-20" />
            </label>
            <label className="text-sm text-gray-500">
              停止条件 <select value={form.stop_condition}
                onChange={e => setForm(p => ({ ...p, stop_condition: e.target.value }))}
                className="ml-1 border rounded px-2 py-1 text-sm">
                <option value="max_ticks">到达最大Tick</option>
                <option value="intercept_success">拦截成功</option>
                <option value="intercept_fail">拦截失败</option>
                <option value="target_lost">目标丢失</option>
              </select>
            </label>
          </div>
          {/* 选择参与实体 */}
          <div>
            <div className="text-sm font-medium text-gray-600 mb-1">参与推演的实体</div>
            {(instances as ObjectInstance[]).length === 0 ? (
              <div className="text-xs text-gray-400">暂无实体实例，请先在"本体空间"Tab 中创建</div>
            ) : (
              <div className="max-h-32 overflow-y-auto border rounded p-2 bg-white space-y-1">
                {(instances as ObjectInstance[]).map(inst => (
                  <label key={inst.id} className="flex items-center gap-2 text-sm cursor-pointer hover:bg-gray-50 px-1 py-0.5 rounded">
                    <input type="checkbox" checked={form.participant_instance_ids.includes(inst.id)}
                      onChange={e => {
                        if (e.target.checked) {
                          setForm(p => ({ ...p, participant_instance_ids: [...p.participant_instance_ids, inst.id] }))
                        } else {
                          setForm(p => ({ ...p, participant_instance_ids: p.participant_instance_ids.filter(id => id !== inst.id) }))
                        }
                      }}
                      className="rounded" />
                    <span>{inst.name_cn}</span>
                    <span className="text-xs text-gray-400">{(inst as any).object_type_id?.slice(0, 6)}...</span>
                  </label>
                ))}
              </div>
            )}
            <div className="text-xs text-gray-400 mt-1">已选 {form.participant_instance_ids.length} 个实体</div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => createMut.mutate(form)}
              disabled={!form.name.trim() || form.participant_instance_ids.length === 0}
              className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed">创建</button>
            <button onClick={() => setShowCreate(false)}
              className="px-3 py-1.5 border text-sm rounded hover:bg-gray-100">取消</button>
          </div>
        </div>
      )}

      {/* 想定列表 */}
      {scenarios.length === 0 ? (
        <div className="text-center text-gray-400 py-12">
          <p className="mb-2">暂无想定</p>
          <p className="text-xs">先在"本体空间"Tab 中创建实体类型和实例，再回来新建推演想定</p>
        </div>
      ) : (
        <div className="space-y-3">
          {(scenarios as Scenario[]).map(s => {
            const st = STATUS_LABELS[s.status] || STATUS_LABELS.draft
            const participantNames = (s.participant_instance_ids || []).map(id => {
              const inst = instanceMap[id]
              return inst ? inst.name_cn : id.slice(0, 8) + '...'
            })
            return (
              <div key={s.id} className="border rounded-lg p-4 hover:shadow-sm transition-shadow">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <button onClick={() => navigate(`/simulation/${s.id}?ontologyId=${ontologyId}`)}
                        className="text-left font-medium hover:text-blue-600 transition-colors truncate">
                        {s.name}
                      </button>
                      <span className={`text-xs px-2 py-0.5 rounded whitespace-nowrap ${st.color}`}>{st.cn}</span>
                    </div>
                    {s.description && <p className="text-sm text-gray-500 mt-1">{s.description}</p>}
                    <div className="flex gap-4 mt-2 text-xs text-gray-400">
                      <span className="inline-flex items-center gap-1"><Clock size={12} /> Tick {s.current_tick}/{s.max_ticks}</span>
                      {participantNames.length > 0 && (
                        <span className="inline-flex items-center gap-1 truncate" title={participantNames.join(', ')}>
                          <Users size={12} /> {participantNames.join(', ')}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 ml-2">
                    {/* 方案按钮 */}
                    <button onClick={() => { setActiveTab('plans'); setSelectedScenario(s.id) }} title="方案管理"
                      className="p-1.5 text-indigo-600 hover:bg-indigo-50 rounded"><Zap size={16} /></button>
                    {/* 查看按钮 — 所有状态都能查看 */}
                    <button onClick={() => navigate(`/simulation/${s.id}?ontologyId=${ontologyId}`)} title="进入推演"
                      className="p-1.5 text-blue-600 hover:bg-blue-50 rounded"><Eye size={16} /></button>

                    {/* 控制按钮 */}
                    {(s.status === 'draft' || s.status === 'paused') && (
                      <button onClick={() => startMut.mutate(s.id)} title="开始/继续推演"
                        className="p-1.5 text-green-600 hover:bg-green-50 rounded"><Play size={16} /></button>
                    )}
                    {s.status === 'running' && (
                      <button onClick={() => pauseMut.mutate(s.id)} title="暂停"
                        className="p-1.5 text-yellow-600 hover:bg-yellow-50 rounded"><Pause size={16} /></button>
                    )}
                    {(s.status !== 'draft') && (
                      <button onClick={() => { if (confirm('确定重置推演？所有记录将被清除')) resetMut.mutate(s.id) }} title="重置"
                        className="p-1.5 text-gray-500 hover:bg-gray-50 rounded"><RotateCcw size={14} /></button>
                    )}
                    <button onClick={() => {
                      setEditSid(s.id)
                      setEditForm({
                        name: s.name, description: s.description || '',
                        max_ticks: s.max_ticks, stop_condition: (s as any).stop_condition || 'max_ticks',
                        participant_instance_ids: [...(s.participant_instance_ids || [])]
                      })
                    }} title="编辑"
                      className="p-1.5 text-gray-400 hover:bg-gray-100 rounded"><Edit3 size={14} /></button>
                    <button onClick={() => { if (confirm('确定删除?')) deleteMut.mutate(s.id) }} title="删除"
                      className="p-1.5 text-red-400 hover:bg-red-50 rounded"><Trash2 size={14} /></button>
                  </div>
                </div>
                {/* 编辑面板 */}
                {editSid === s.id && (
                  <div className="mt-3 pt-3 border-t space-y-2">
                    <input value={editForm.name} onChange={e => setEditForm(p => ({ ...p, name: e.target.value }))}
                      className="w-full border rounded px-2 py-1 text-sm" placeholder="名称" />
                    <textarea value={editForm.description} onChange={e => setEditForm(p => ({ ...p, description: e.target.value }))}
                      className="w-full border rounded px-2 py-1 text-sm" rows={2} placeholder="描述" />
                    <div className="flex gap-3 text-sm">
                      <label>最大Tick <input type="number" value={editForm.max_ticks}
                        onChange={e => setEditForm(p => ({ ...p, max_ticks: +e.target.value }))}
                        className="ml-1 border rounded px-1 py-0.5 w-16" /></label>
                      <label>停止条件 <select value={editForm.stop_condition}
                        onChange={e => setEditForm(p => ({ ...p, stop_condition: e.target.value }))}
                        className="ml-1 border rounded px-1 py-0.5 text-xs">
                        <option value="max_ticks">到达最大Tick</option>
                        <option value="intercept_success">拦截成功</option>
                        <option value="intercept_fail">拦截失败</option>
                        <option value="target_lost">目标丢失</option>
                      </select></label>
                    </div>
                    <div className="text-xs text-gray-500">参与实体</div>
                    <div className="max-h-24 overflow-y-auto border rounded p-1 space-y-0.5">
                      {(instances as ObjectInstance[]).map(inst => (
                        <label key={inst.id} className="flex items-center gap-1.5 text-xs cursor-pointer hover:bg-gray-50 px-1 rounded">
                          <input type="checkbox" checked={editForm.participant_instance_ids.includes(inst.id)}
                            onChange={e => {
                              if (e.target.checked) setEditForm(p => ({ ...p, participant_instance_ids: [...p.participant_instance_ids, inst.id] }))
                              else setEditForm(p => ({ ...p, participant_instance_ids: p.participant_instance_ids.filter(id => id !== inst.id) }))
                            }} />
                          {inst.name_cn}
                        </label>
                      ))}
                    </div>
                    <div className="flex gap-1">
                      <button onClick={() => updateMut.mutate({ id: s.id, data: editForm })}
                        className="px-2 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 inline-flex items-center gap-1"><Save size={12} />保存</button>
                      <button onClick={() => setEditSid(null)}
                        className="px-2 py-1 border text-xs rounded hover:bg-gray-100 inline-flex items-center gap-1"><X size={12} />取消</button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
