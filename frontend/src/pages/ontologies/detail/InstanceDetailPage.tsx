import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ontologyApi } from '@/api/ontologies'
import { ArrowLeft, Pencil, Save, X, Plus, Code2, Zap, Trash2, Box, Play, RefreshCw, Link2, Database } from 'lucide-react'
import { apiClientV2 } from '@/api/client'
import type { ObjectType, ObjectInstance } from '@/types/ontology'

export default function InstanceDetailPage() {
  const { id: ontologyId, typeId, instId } = useParams<{ id: string; typeId: string; instId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: types = [] } = useQuery({ queryKey: ['object-types', ontologyId], queryFn: () => ontologyApi.listObjectTypes(ontologyId!) as Promise<ObjectType[]>, enabled: !!ontologyId })
  const { data: instances = [] } = useQuery({ queryKey: ['object-instances', ontologyId], queryFn: () => ontologyApi.listInstances(ontologyId!) as Promise<ObjectInstance[]>, enabled: !!ontologyId })
  const { data: rules = [] } = useQuery({ queryKey: ['object-rules', ontologyId], queryFn: () => ontologyApi.listRules(ontologyId!).then((r: any) => Array.isArray(r) ? r : (r?.data || [])), enabled: !!ontologyId })
  const { data: actions = [] } = useQuery({ queryKey: ['object-actions', ontologyId], queryFn: () => ontologyApi.listActionsV2(ontologyId!).then((r: any) => Array.isArray(r) ? r : (r?.data || [])), enabled: !!ontologyId })

  const inst = (instances as ObjectInstance[]).find(i => i.id === instId)
  const type = (types as ObjectType[]).find(t => t.id === typeId)
  const instRules = (rules as any[]).filter((r: any) => r.object_instance_id === instId)
  const instActions = (actions as any[]).filter((a: any) => a.object_instance_id === instId)
  const schema = (type?.property_schema || {}) as Record<string, { type: string; unit?: string }>

  const [editing, setEditing] = useState(false)
  const [editPropsOnly, setEditPropsOnly] = useState(false)
  const [newField, setNewField] = useState({ name: '', type: 'string', unit: '' })
  const [form, setForm] = useState({ name_cn: '', name_en: '', description: '' })
  const [editProps, setEditProps] = useState<Record<string, string>>({})
  const [ruleEditor, setRuleEditor] = useState<{ editId?: string } | null>(null)
  const [ruleForm, setRuleForm] = useState({ name_cn: '', description: '', python_code: 'def check(context: dict) -> dict:\n    return {"passed": True, "message": "ok"}\n' })
  const [actionEditor, setActionEditor] = useState<{ editId?: string } | null>(null)
  const [actionForm, setActionForm] = useState({ name_cn: '', description: '', python_code: 'def execute(context: dict) -> dict:\n    return {"status": "done"}\n' })
  const [triggerReport, setTriggerReport] = useState<any>(null)
  const [triggerLoading, setTriggerLoading] = useState(false)
  const [showBindPicker, setShowBindPicker] = useState<string | null>(null)
  const [dataSources, setDataSources] = useState<any[]>([])
  const [bindTableData, setBindTableData] = useState<any>(null) // {columns, rows}
  const [bindSource, setBindSource] = useState<any>(null)

  const updateInstMut = useMutation({ mutationFn: ({ id, data }: { id: string; data: any }) => ontologyApi.updateInstance(ontologyId!, id, data), onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-instances', ontologyId] }); setEditing(false) } })
  const deleteRuleMut = useMutation({ mutationFn: (id: string) => ontologyApi.deleteRule(ontologyId!, id), onSuccess: () => qc.invalidateQueries({ queryKey: ['object-rules', ontologyId] }) })
  const deleteActionMut = useMutation({ mutationFn: (id: string) => ontologyApi.deleteActionV2(ontologyId!, id), onSuccess: () => qc.invalidateQueries({ queryKey: ['object-actions', ontologyId] }) })
  const createRuleMut = useMutation({ mutationFn: (d: any) => ontologyApi.createRule(ontologyId!, d), onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-rules', ontologyId] }); setRuleEditor(null) } })
  const updateRuleMut = useMutation({ mutationFn: ({ id, data }: { id: string; data: any }) => ontologyApi.updateRule(ontologyId!, id, data), onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-rules', ontologyId] }); setRuleEditor(null) } })
  const createActionMut = useMutation({ mutationFn: (d: any) => ontologyApi.createActionV2(ontologyId!, d), onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-actions', ontologyId] }); setActionEditor(null) } })
  const updateActionMut = useMutation({ mutationFn: ({ id, data }: { id: string; data: any }) => ontologyApi.updateActionV2(ontologyId!, id, data), onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-actions', ontologyId] }); setActionEditor(null) } })

  if (!inst || !type) return <div className="p-6 text-gray-400">加载中...</div>

  function startEdit() {
    setForm({ name_cn: inst!.name_cn, name_en: inst!.name_en || '', description: inst!.description || '' })
    const vals: Record<string, string> = {}
    Object.entries(inst!.properties || {}).forEach(([k, v]) => { vals[k] = String(v ?? '') })
    setEditProps(vals)
    setEditing(true)
  }
  function buildProps() {
    const props: any = {}
    Object.entries(editProps).forEach(([k, v]) => {
      const def = schema[k]
      if (def?.type === 'number') { const n = parseFloat(v); if (!isNaN(n)) props[k] = n; else if (v) props[k] = v }
      else if (v) props[k] = v
    })
    return props
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={() => navigate(`/ontologies/${ontologyId}/types/${typeId}`)} className="text-gray-500 hover:text-black text-sm flex items-center gap-1">
          <ArrowLeft size={14} /> 返回 {type.name_cn}
        </button>
      </div>

      {/* Basic Info */}
      <div className="bg-white border rounded-xl p-6">
        {editing ? (
          <div className="space-y-3">
            <input value={form.name_cn} onChange={e => setForm({ ...form, name_cn: e.target.value })} placeholder="中文名" className="w-full border rounded-lg px-3 py-2 text-sm font-semibold" />
            <input value={form.name_en} onChange={e => setForm({ ...form, name_en: e.target.value })} placeholder="英文名" className="w-full border rounded-lg px-3 py-2 text-sm" />
            <input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="描述" className="w-full border rounded-lg px-3 py-2 text-sm" />
            {Object.keys(schema).length > 0 && (
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(schema).map(([name, def]) => (
                  <div key={name}><label className="block text-[10px] text-gray-500 mb-0.5">{name}{def.unit ? ` (${def.unit})` : ''}</label>
                    {def.type === 'boolean' ? (
                      <select value={editProps[name] || ''} onChange={e => setEditProps({ ...editProps, [name]: e.target.value })} className="w-full border rounded px-2 py-1 text-xs"><option value="">—</option><option value="true">是</option><option value="false">否</option></select>
                    ) : def.type === 'number' ? (
                      <div className="flex items-center gap-1">
                        <input type="number" value={editProps[name] || ''} onChange={e => setEditProps({ ...editProps, [name]: e.target.value })} className="flex-1 border rounded px-2 py-1 text-xs" />
                        <button onClick={async () => { setShowBindPicker(name); const r = await ontologyApi.listDataSources(ontologyId!); const sources = Array.isArray(r) ? r : (r?.data || []); setDataSources(sources); setBindTableData(null); setBindSource(null) }}
                          className="text-gray-300 hover:text-blue-500 p-0.5" title="从数据源取值"><Link2 size={10} /></button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1">
                        <input value={editProps[name] || ''} onChange={e => setEditProps({ ...editProps, [name]: e.target.value })} className="flex-1 border rounded px-2 py-1 text-xs" />
                        <button onClick={async () => { setShowBindPicker(name); const r = await ontologyApi.listDataSources(ontologyId!); const sources = Array.isArray(r) ? r : (r?.data || []); setDataSources(sources); setBindTableData(null); setBindSource(null) }}
                          className="text-gray-300 hover:text-blue-500 p-0.5" title="从数据源取值"><Link2 size={10} /></button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <button onClick={() => updateInstMut.mutate({ id: instId!, data: { name_cn: form.name_cn, name_en: form.name_en, description: form.description, properties: buildProps() } })} className="flex items-center gap-1 px-3 py-1.5 bg-black text-white rounded-lg text-sm"><Save size={12} /> 保存</button>
              <button onClick={() => setEditing(false)} className="px-3 py-1.5 border rounded-lg text-sm text-gray-500"><X size={12} /> 取消</button>
            </div>
          </div>
        ) : (
          <div>
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-gray-900">{inst.name_cn}</h2>
                {inst.name_en && <p className="text-sm text-gray-400 font-mono">{inst.name_en}</p>}
              </div>
              <button onClick={startEdit} className="text-gray-400 hover:text-gray-600"><Pencil size={16} /></button>
            </div>
            {inst.description && <p className="text-sm text-gray-500 mt-3">{inst.description}</p>}
            <p className="text-xs text-gray-400 mt-2">所属本体：<span className="text-blue-600 cursor-pointer hover:underline" onClick={() => navigate(`/ontologies/${ontologyId}/types/${typeId}`)}>{type.name_cn}</span></p>
          </div>
        )}
      </div>

      {/* Trigger Rules */}
      <div className="bg-white border rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-sm text-gray-800">规则引擎</h3>
          <button onClick={async () => {
            setTriggerLoading(true)
            try {
              const res: any = await ontologyApi.triggerRules(ontologyId!, instId!)
              setTriggerReport(res)
            } catch (e: any) { alert('触发失败: ' + String(e)) }
            finally { setTriggerLoading(false) }
          }}
            className="px-3 py-1.5 bg-purple-600 text-white rounded-lg text-xs flex items-center gap-1 hover:bg-purple-700">
            <RefreshCw size={12} className={triggerLoading ? 'animate-spin' : ''} /> 触发规则检查
          </button>
        </div>
        {!triggerReport ? (
          <p className="text-sm text-gray-400">点击按钮执行该实体关联的规则和动作</p>
        ) : (
          <div className="space-y-2 text-sm">
            <p className="text-gray-600">检查了 <b>{triggerReport.total_rules_checked}</b> 条规则，触发 <b>{triggerReport.triggered?.length || 0}</b> 条</p>
            {(triggerReport.triggered || []).map((t: any, i: number) => (
              <div key={i} className="border rounded-lg p-3 bg-purple-50">
                <p className="font-medium text-purple-800">◇ {t.rule_name}</p>
                {t.rule_message && <p className="text-xs text-purple-600 mt-0.5">{t.rule_message}</p>}
                {(t.actions || []).map((a: any, j: number) => {
                  const pending = a.links_to_create || []
                  return (
                    <div key={j} className="mt-1">
                      <div className="flex items-center gap-1 text-xs text-amber-700">
                        <Zap size={10} /> {a.action_name} — {a.status}
                        {a.message && <span className="text-gray-500">({a.message})</span>}
                      </div>
                      {pending.length > 0 && (
                        <div className="mt-2 ml-4">
                          <div className="text-[10px] text-gray-500 mb-1">待创建 {pending.length} 条连线：</div>
                          {pending.map((l: any, k: number) => (
                            <div key={k} className="text-[10px] text-gray-600 ml-2">
                              {l.link_type}: {l.source_instance_id?.slice(0,8)} → {l.target_instance_id?.slice(0,8)}
                            </div>
                          ))}
                          <button onClick={async () => {
                            try {
                              const allLinks = triggerReport.triggered.flatMap((x: any) => (x.actions || []).flatMap((y: any) => y.links_to_create || []))
                              const res: any = await ontologyApi.confirmLinks(ontologyId!, allLinks)
                              qc.invalidateQueries({queryKey:['links-list',ontologyId]})
                              alert(`已创建 ${res.created} 条连线`)
                              setTriggerReport(null)
                            } catch (e: any) { alert('创建失败: ' + String(e)) }
                          }}
                            className="mt-2 px-3 py-1 bg-green-600 text-white rounded text-xs hover:bg-green-700">
                            确认创建连线
                          </button>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Properties */}
      <div className="bg-white border rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-sm text-gray-800">属性值</h3>
          {Object.keys(schema).length > 0 && !editPropsOnly && !editing && (
            <div className="flex items-center gap-2">
              <button onClick={async () => {
                // 查看绑定列的最新数据
                const dsList: any = await ontologyApi.listDataSources(ontologyId!)
                const sources = Array.isArray(dsList) ? dsList : (dsList?.data || [])
                const boundProps = Object.entries(inst.properties || {}).filter(([, v]) => String(v).startsWith('__bind__|'))
                if (boundProps.length === 0) { alert('没有绑定属性'); return }
                const parts = String(boundProps[0][1]).split('|')
                const dsName = parts[1], table = parts[2]
                const ds = sources.find((x: any) => x.name === dsName || x.id === dsName)
                if (!ds) { alert(`数据源未找到 "${dsName}"，可用: ${sources.map((x:any)=>x.name).join(', ') || '无'}`); return }
                try {
                  const res: any = await apiClientV2.post('/db/preview', ds.db_config, { params: { table_name: table, limit: 50 } })
                  const lines = (res?.rows || []).map((r: any) =>
                    boundProps.map(([propName, propVal]) => {
                      const col = String(propVal).split('|').pop() || ''
                      return `${propName}=${r[col] ?? '-'}`
                    }).join(', ')
                  ).join('\n')
                  alert(`最新数据 (${table}):\n${lines || '无数据'}`)
                } catch(e: any) { alert('取数据失败: ' + String(e)) }
              }}
                className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"><RefreshCw size={12} /> 查看列数据</button>
              <button onClick={() => { const vals: Record<string,string>={}; Object.entries(inst.properties||{}).forEach(([k,v])=>{vals[k]=String(v??'')}); setEditProps(vals); setEditPropsOnly(true) }}
                className="text-gray-400 hover:text-gray-600"><Pencil size={14} /></button>
            </div>
          )}
        </div>
        {editPropsOnly ? (
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(editProps).map(([name, v]) => (
                <div key={name} className="flex items-center gap-1">
                  <div className="flex-1">
                    <label className="block text-[10px] text-gray-500 mb-0.5">{name}{schema[name]?.unit ? ` (${schema[name].unit})` : ''}{!schema[name] ? <span className="text-amber-500 ml-1">(实例独有)</span> : null}</label>
                    {schema[name]?.type === 'boolean' ? (
                      <select value={v} onChange={e => setEditProps({ ...editProps, [name]: e.target.value })} className="w-full border rounded px-2 py-1 text-xs"><option value="">—</option><option value="true">是</option><option value="false">否</option></select>
                    ) : schema[name]?.type === 'number' ? (
                      <div className="flex items-center gap-1">
                        <input type="number" value={v} onChange={e => setEditProps({ ...editProps, [name]: e.target.value })} className="flex-1 border rounded px-2 py-1 text-xs" />
                        <button onClick={async () => { setShowBindPicker(name); const r = await ontologyApi.listDataSources(ontologyId!); const s = Array.isArray(r) ? r : (r?.data || []); setDataSources(s); setBindTableData(null); setBindSource(null) }}
                          className="text-gray-300 hover:text-blue-500 p-0.5" title="从数据源取值"><Link2 size={10} /></button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1">
                        <input value={v} onChange={e => setEditProps({ ...editProps, [name]: e.target.value })} className="flex-1 border rounded px-2 py-1 text-xs" />
                        <button onClick={async () => { setShowBindPicker(name); const r = await ontologyApi.listDataSources(ontologyId!); const s = Array.isArray(r) ? r : (r?.data || []); setDataSources(s); setBindTableData(null); setBindSource(null) }}
                          className="text-gray-300 hover:text-blue-500 p-0.5" title="从数据源取值"><Link2 size={10} /></button>
                      </div>
                    )}
                  </div>
                  <button onClick={() => { const n = { ...editProps }; delete n[name]; setEditProps(n) }}
                    className="text-gray-300 hover:text-red-500 self-end mb-0.5"><Trash2 size={10} /></button>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-2 border-t pt-2">
              <input value={newField.name} onChange={e => setNewField({ ...newField, name: e.target.value })} placeholder="新属性名" className="flex-1 border rounded px-2 py-1 text-xs" />
              <select value={newField.type} onChange={e => setNewField({ ...newField, type: e.target.value })} className="border rounded px-2 py-1 text-xs w-18"><option value="string">文本</option><option value="number">数字</option><option value="boolean">布尔</option></select>
              <input value={newField.unit} onChange={e => setNewField({ ...newField, unit: e.target.value })} placeholder="单位" className="border rounded px-2 py-1 text-xs w-14" />
              <button onClick={() => { if (!newField.name) return; setEditProps({ ...editProps, [newField.name]: '' }); setNewField({ name: '', type: 'string', unit: '' }) }}
                className="text-xs text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50 flex-shrink-0"><Plus size={12} /> 添加</button>
            </div>
            <div className="flex gap-2">
              <button onClick={() => updateInstMut.mutate({ id: instId!, data: { properties: buildProps() } })} className="px-3 py-1.5 bg-black text-white rounded-lg text-xs"><Save size={12} /> 保存</button>
              <button onClick={() => setEditPropsOnly(false)} className="px-3 py-1.5 border rounded-lg text-xs text-gray-500">取消</button>
            </div>
          </div>
        ) : Object.keys(inst.properties || {}).length === 0 ? (
          <p className="text-sm text-gray-400">暂无属性值，点击右上角铅笔编辑</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {Object.entries(inst.properties || {}).map(([name, value]) => {
              const isBound = String(value).startsWith('__bind__|')
              return (
                <span key={name} className={`inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-mono ${isBound ? 'bg-green-50 text-green-700' : 'bg-blue-50 text-blue-700'}`}>
                  {isBound ? <Link2 size={10} className="text-green-500" /> : null}
                  {name}={isBound ? `📶${String(value).split('|').pop()}` : String(value)}{schema[name]?.unit ? ` ${schema[name].unit}` : ''}
                </span>
              )
            })}
          </div>
        )}
      </div>

      {/* Rules */}
      <div className="bg-white border rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b">
          <div><h3 className="font-semibold text-sm text-gray-800">规则 ({instRules.length})</h3><p className="text-xs text-gray-400 mt-0.5">实体层规则，仅适用于该实体</p></div>
          <button onClick={() => { setRuleEditor({}); setRuleForm({ name_cn: '', description: '', python_code: 'def check(context: dict) -> dict:\n    return {"passed": True, "message": "ok"}\n' }) }}
            className="px-3 py-1.5 border rounded-lg text-xs text-gray-600 hover:bg-gray-50 flex items-center gap-1"><Plus size={12} /> 新增规则</button>
        </div>
        <div>
          {instRules.length === 0 ? <div className="px-5 py-6 text-center text-sm text-gray-400">暂无规则</div> : (
            instRules.map((r: any) => (
              <div key={r.id} className="flex items-center px-5 py-2.5 border-t hover:bg-gray-50 group cursor-pointer"
                onClick={() => { setRuleEditor({ editId: r.id }); setRuleForm({ name_cn: r.name_cn, description: r.description || '', python_code: r.python_code || '' }) }}>
                <Code2 size={12} className="text-purple-500 mr-2 flex-shrink-0" />
                <span className="flex-1 text-sm text-gray-800">{r.name_cn}</span>
                {r.description && <span className="text-xs text-gray-400 mr-2 truncate">— {r.description}</span>}
                <button onClick={(e) => { e.stopPropagation(); if (confirm(`删除规则"${r.name_cn}"？`)) deleteRuleMut.mutate(r.id) }}
                  className="text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100"><Trash2 size={14} /></button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="bg-white border rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b">
          <div><h3 className="font-semibold text-sm text-gray-800">动作 ({instActions.length})</h3><p className="text-xs text-gray-400 mt-0.5">实体层动作，仅适用于该实体</p></div>
          <button onClick={() => { setActionEditor({}); setActionForm({ name_cn: '', description: '', python_code: 'def execute(context: dict) -> dict:\n    return {"status": "done"}\n' }) }}
            className="px-3 py-1.5 border rounded-lg text-xs text-gray-600 hover:bg-gray-50 flex items-center gap-1"><Plus size={12} /> 新增动作</button>
        </div>
        <div>
          {instActions.length === 0 ? <div className="px-5 py-6 text-center text-sm text-gray-400">暂无动作</div> : (
            instActions.map((a: any) => (
              <div key={a.id} className="flex items-center px-5 py-2.5 border-t hover:bg-gray-50 group cursor-pointer"
                onClick={() => { setActionEditor({ editId: a.id }); setActionForm({ name_cn: a.name_cn, description: a.description || '', python_code: a.python_code || '' }) }}>
                <Zap size={12} className="text-amber-500 mr-2 flex-shrink-0" />
                <span className="flex-1 text-sm text-gray-800">{a.name_cn}</span>
                {a.description && <span className="text-xs text-gray-400 mr-2 truncate">— {a.description}</span>}
                <button onClick={(e) => { e.stopPropagation(); if (confirm(`删除动作"${a.name_cn}"？`)) deleteActionMut.mutate(a.id) }}
                  className="text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100"><Trash2 size={14} /></button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Rule Editor Modal */}
      {ruleEditor && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setRuleEditor(null)}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-auto m-4" onClick={e => e.stopPropagation()}>
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between"><h3 className="font-semibold text-gray-800">{ruleEditor.editId ? '编辑规则' : '新增规则'} — 实体层</h3><button onClick={() => setRuleEditor(null)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button></div>
              <input value={ruleForm.name_cn} onChange={e => setRuleForm({ ...ruleForm, name_cn: e.target.value })} placeholder="规则名称 *" className="w-full border rounded-lg px-3 py-2 text-sm" />
              <input value={ruleForm.description} onChange={e => setRuleForm({ ...ruleForm, description: e.target.value })} placeholder="描述（可选）" className="w-full border rounded-lg px-3 py-2 text-sm" />
              <div className="relative">
                <textarea value={ruleForm.python_code} onChange={e => setRuleForm({ ...ruleForm, python_code: e.target.value })} rows={12} spellCheck={false}
                  className="w-full border rounded-lg px-3 py-3 text-sm font-mono bg-gray-900 text-green-400 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-y" />
                <button onClick={() => { try { Function('"use strict"; return (' + ruleForm.python_code + ')')(); alert('语法检查通过') } catch (e: any) { alert('语法错误：' + e.message) } }}
                  className="absolute top-2 right-2 flex items-center gap-1 text-[10px] bg-gray-700 text-gray-300 hover:text-white px-2 py-1 rounded"><Play size={10} /> 测试语法</button>
              </div>
              <div className="flex gap-2 justify-end">
                {ruleEditor.editId ? (
                  <button onClick={() => updateRuleMut.mutate({ id: ruleEditor.editId!, data: ruleForm })} disabled={!ruleForm.name_cn} className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 更新</button>
                ) : (
                  <button onClick={() => createRuleMut.mutate({ ...ruleForm, object_instance_id: instId })} disabled={!ruleForm.name_cn} className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 创建</button>
                )}
                <button onClick={() => setRuleEditor(null)} className="px-4 py-2 border rounded-lg text-sm text-gray-500">取消</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Action Editor Modal */}
      {actionEditor && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setActionEditor(null)}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-auto m-4" onClick={e => e.stopPropagation()}>
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between"><h3 className="font-semibold text-gray-800">{actionEditor.editId ? '编辑动作' : '新增动作'} — 实体层</h3><button onClick={() => setActionEditor(null)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button></div>
              <input value={actionForm.name_cn} onChange={e => setActionForm({ ...actionForm, name_cn: e.target.value })} placeholder="动作名称 *" className="w-full border rounded-lg px-3 py-2 text-sm" />
              <input value={actionForm.description} onChange={e => setActionForm({ ...actionForm, description: e.target.value })} placeholder="描述（可选）" className="w-full border rounded-lg px-3 py-2 text-sm" />
              <div className="relative">
                <textarea value={actionForm.python_code} onChange={e => setActionForm({ ...actionForm, python_code: e.target.value })} rows={12} spellCheck={false}
                  className="w-full border rounded-lg px-3 py-3 text-sm font-mono bg-gray-900 text-green-400 focus:outline-none focus:ring-2 focus:ring-amber-500 resize-y" />
                <button onClick={() => { try { Function('"use strict"; return (' + actionForm.python_code + ')')(); alert('语法检查通过') } catch (e: any) { alert('语法错误：' + e.message) } }}
                  className="absolute top-2 right-2 flex items-center gap-1 text-[10px] bg-gray-700 text-gray-300 hover:text-white px-2 py-1 rounded"><Play size={10} /> 测试语法</button>
              </div>
              <div className="flex gap-2 justify-end">
                {actionEditor.editId ? (
                  <button onClick={() => updateActionMut.mutate({ id: actionEditor.editId!, data: actionForm })} disabled={!actionForm.name_cn} className="px-4 py-2 bg-amber-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 更新</button>
                ) : (
                  <button onClick={() => createActionMut.mutate({ ...actionForm, object_instance_id: instId })} disabled={!actionForm.name_cn} className="px-4 py-2 bg-amber-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 创建</button>
                )}
                <button onClick={() => setActionEditor(null)} className="px-4 py-2 border rounded-lg text-sm text-gray-500">取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
      {/* 数据绑定选择器 */}
      {showBindPicker && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setShowBindPicker(null)}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md max-h-[70vh] overflow-auto m-4" onClick={e => e.stopPropagation()}>
            <div className="p-4 space-y-3">
              <h4 className="font-semibold text-sm">选择数据源列 — 绑定到「{showBindPicker}」</h4>
              <div className="space-y-2">
                {dataSources.length === 0 && <p className="text-xs text-gray-400 px-1">暂无数据源，请先在「数据库」标签页保存</p>}
                {dataSources.map((ds: any) => (
                  <button key={ds.id} onClick={async () => {
                    setBindSource(ds)
                    try {
                      const res: any = await apiClientV2.post('/db/preview', ds.db_config, { params: { table_name: ds.registered_table, limit: 50 } })
                      setBindTableData(res)
                    } catch(e) { alert('加载失败: ' + String(e)) }
                  }}
                    className={`w-full text-left px-3 py-1.5 text-xs rounded ${bindSource?.id === ds.id ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-50 text-gray-600'}`}>
                    <Database size={12} className="inline mr-1" />{ds.name}
                  </button>
                ))}
                {bindTableData && (
                  <div className="border-t pt-2 mt-2">
                    <p className="text-[10px] text-gray-400 mb-1">{bindSource?.name} — 点击单元格选择值</p>
                    <div className="overflow-auto max-h-64 max-w-full border rounded">
                      <table className="text-[10px] w-full">
                        <thead>
                          <tr className="bg-gray-100 sticky top-0">
                            <th className="px-1.5 py-1 text-left text-gray-500 font-medium border-r">#</th>
                            {bindTableData.columns?.map((c: string) => (
                              <th key={c} onClick={() => {
                                  const dsName = bindSource?.name || ''
                                  const tbl = bindSource?.registered_table || ''
                                  const lookupCol = bindTableData.columns?.[0] || 'id'
                                  const binding = `__bind__|${dsName}|${tbl}|${lookupCol}|${c}`
                                  setEditProps({ ...editProps, [showBindPicker!]: binding })
                                  setShowBindPicker(null)
                                }}
                                className="px-1.5 py-1 text-left text-gray-500 font-medium border-r whitespace-nowrap cursor-pointer hover:bg-blue-100" title="绑定此列（动态）">{c} 🔗</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {bindTableData.rows?.map((row: any, i: number) => (
                            <tr key={i} className="hover:bg-blue-50 border-t">
                              <td className="px-1.5 py-0.5 text-gray-400 border-r">{i + 1}</td>
                              {bindTableData.columns?.map((c: string) => (
                                <td key={c} onClick={() => {
                                  const val = row[c] != null ? String(row[c]) : ''
                                  setEditProps({ ...editProps, [showBindPicker!]: val })
                                  setShowBindPicker(null)
                                }}
                                  className="px-1.5 py-0.5 border-r cursor-pointer hover:bg-blue-100 whitespace-nowrap text-gray-700">
                                  {row[c] != null ? String(row[c]) : <span className="text-gray-300">—</span>}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
              <button onClick={() => setShowBindPicker(null)} className="w-full py-2 border rounded-lg text-sm text-gray-500">取消</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
