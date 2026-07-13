import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ontologyApi } from '@/api/ontologies'
import { ArrowLeft, Pencil, Save, X, Plus, Code2, Zap, Trash2, Box, Play } from 'lucide-react'
import type { ObjectType, ObjectInstance } from '@/types/ontology'

export default function TypeDetailPage() {
  const { id: ontologyId, typeId } = useParams<{ id: string; typeId: string }>()
  const navigate = useNavigate()
  const [ruleEditor, setRuleEditor] = useState<{ editId?: string } | null>(null)
  const [ruleForm, setRuleForm] = useState({ name_cn: '', description: '', python_code: 'def check(context: dict) -> dict:\n    return {"passed": True, "message": "ok"}\n' })
  const [actionEditor, setActionEditor] = useState<{ editId?: string } | null>(null)
  const [actionForm, setActionForm] = useState({ name_cn: '', description: '', python_code: 'def execute(context: dict) -> dict:\n    return {"status": "done"}\n' })
  const qc = useQueryClient()

  const { data: types = [] } = useQuery({ queryKey: ['object-types', ontologyId], queryFn: () => ontologyApi.listObjectTypes(ontologyId!) as Promise<ObjectType[]>, enabled: !!ontologyId })
  const { data: instances = [] } = useQuery({ queryKey: ['object-instances', ontologyId], queryFn: () => ontologyApi.listInstances(ontologyId!) as Promise<ObjectInstance[]>, enabled: !!ontologyId })
  const { data: rulesResp } = useQuery({ queryKey: ['object-rules', ontologyId], queryFn: () => ontologyApi.listRules(ontologyId!).then((r: any) => Array.isArray(r) ? r : (r?.data || [])), enabled: !!ontologyId })
  const { data: actionsResp } = useQuery({ queryKey: ['object-actions', ontologyId], queryFn: () => ontologyApi.listActionsV2(ontologyId!).then((r: any) => Array.isArray(r) ? r : (r?.data || [])), enabled: !!ontologyId })

  const type = (types as ObjectType[]).find(t => t.id === typeId)
  const typeInstances = (instances as ObjectInstance[]).filter(i => i.object_type_id === typeId)
  const typeRules = (rulesResp as any[] || []).filter((r: any) => r.object_type_id === typeId && !r.object_instance_id)
  const typeActions = (actionsResp as any[] || []).filter((a: any) => a.object_type_id === typeId && !a.object_instance_id)

  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ name_cn: '', name_en: '', description: '' })
  const [typeFields, setTypeFields] = useState<{key:string;name:string;type:string;unit:string}[]>([])
  const [showInstForm, setShowInstForm] = useState(false)
  const [editInstId, setEditInstId] = useState<string | null>(null)
  const [instForm, setInstForm] = useState({ name_cn: '', name_en: '', description: '' })
  const [instProps, setInstProps] = useState<Record<string, string>>({})

  const updateTypeMut = useMutation({
    mutationFn: (data: any) => ontologyApi.updateObjectType(ontologyId!, typeId!, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-types', ontologyId] }); setEditing(false) }
  })
  const createInstMut = useMutation({
    mutationFn: (data: any) => ontologyApi.createInstance(ontologyId!, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-instances', ontologyId] }); setShowInstForm(false) }
  })
  const deleteInstMut = useMutation({
    mutationFn: (id: string) => ontologyApi.deleteInstance(ontologyId!, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['object-instances', ontologyId] })
  })
  const deleteRuleMut = useMutation({
    mutationFn: (id: string) => ontologyApi.deleteRule(ontologyId!, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['object-rules', ontologyId] })
  })
  const deleteActionMut = useMutation({
    mutationFn: (id: string) => ontologyApi.deleteActionV2(ontologyId!, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['object-actions', ontologyId] })
  })
  const createRuleMut = useMutation({ mutationFn: (d: any) => ontologyApi.createRule(ontologyId!, d), onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-rules', ontologyId] }); setRuleEditor(null) } })
  const updateRuleMut = useMutation({ mutationFn: ({ id, data }: { id: string; data: any }) => ontologyApi.updateRule(ontologyId!, id, data), onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-rules', ontologyId] }); setRuleEditor(null) } })
  const createActionMut = useMutation({ mutationFn: (d: any) => ontologyApi.createActionV2(ontologyId!, d), onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-actions', ontologyId] }); setActionEditor(null) } })
  const updateActionMut = useMutation({ mutationFn: ({ id, data }: { id: string; data: any }) => ontologyApi.updateActionV2(ontologyId!, id, data), onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-actions', ontologyId] }); setActionEditor(null) } })

  if (!type) return <div className="p-6 text-gray-400">加载中...</div>

  function startEdit() {
    setForm({ name_cn: type!.name_cn, name_en: type!.name_en || '', description: type!.description || '' })
    const fs: {key:string;name:string;type:string;unit:string}[] = []; let i = 0
    Object.entries(type!.property_schema || {}).forEach(([n, d]: [string, any]) => { fs.push({ key: `f-${i++}`, name: n, type: d.type || 'string', unit: d.unit || '' }) })
    setTypeFields(fs)
    setEditing(true)
  }
  function buildSchema() {
    const s: Record<string, { type: string; unit?: string }> = {}
    typeFields.forEach(f => { if (f.name.trim()) s[f.name.trim()] = { type: f.type, unit: f.unit || undefined } })
    return s
  }
  function startEditInst(oi: ObjectInstance) {
    setEditInstId(oi.id)
    setInstForm({ name_cn: oi.name_cn, name_en: oi.name_en || '', description: oi.description || '' })
    const vals: Record<string, string> = {}
    Object.entries(oi.properties || {}).forEach(([k, v]) => { vals[k] = String(v ?? '') })
    setInstProps(vals)
  }
  const updateInstMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => ontologyApi.updateInstance(ontologyId!, id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-instances', ontologyId] }); setEditInstId(null) }
  })

  function openInstForm() {
    setShowInstForm(true)
    setInstForm({ name_cn: '', name_en: '', description: '' })
    const schema = type!.property_schema || {}
    const vals: Record<string, string> = {}
    Object.keys(schema).forEach(k => { vals[k] = '' })
    setInstProps(vals)
  }

  const schema = (type.property_schema || {}) as Record<string, { type: string; unit?: string }>

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate(`/ontologies/${ontologyId}?tab=ontology-space`)} className="text-gray-500 hover:text-black text-sm flex items-center gap-1">
          <ArrowLeft size={14} /> 返回本体空间
        </button>
      </div>

      {/* Basic Info */}
      <div className="bg-white border rounded-xl p-6">
        {editing ? (
          <div className="space-y-3">
            <input value={form.name_cn} onChange={e => setForm({ ...form, name_cn: e.target.value })}
              placeholder="中文名" className="w-full border rounded-lg px-3 py-2 text-sm font-semibold" />
            <input value={form.name_en} onChange={e => setForm({ ...form, name_en: e.target.value })}
              placeholder="英文名" className="w-full border rounded-lg px-3 py-2 text-sm" />
            <input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
              placeholder="描述" className="w-full border rounded-lg px-3 py-2 text-sm" />
            <div className="border-t pt-3 space-y-2">
              <div className="flex items-center justify-between"><p className="text-xs font-medium text-gray-500">属性字段</p>
                <button onClick={() => setTypeFields(p => [...p, { key: `f-${Date.now()}`, name: '', type: 'string', unit: '' }])} className="text-xs text-blue-600 hover:text-blue-800">+ 添加字段</button>
              </div>
              {typeFields.map(f => (
                <div key={f.key} className="flex items-center gap-2">
                  <input value={f.name} onChange={e => setTypeFields(p => p.map(x => x.key === f.key ? { ...x, name: e.target.value } : x))} placeholder="字段名" className="flex-1 border rounded px-2 py-1 text-xs" />
                  <select value={f.type} onChange={e => setTypeFields(p => p.map(x => x.key === f.key ? { ...x, type: e.target.value } : x))} className="border rounded px-2 py-1 text-xs w-18"><option value="string">文本</option><option value="number">数字</option><option value="boolean">布尔</option></select>
                  <input value={f.unit} onChange={e => setTypeFields(p => p.map(x => x.key === f.key ? { ...x, unit: e.target.value } : x))} placeholder="单位" className="border rounded px-2 py-1 text-xs w-14" />
                  <button onClick={() => setTypeFields(p => p.filter(x => x.key !== f.key))} className="text-gray-300 hover:text-red-500"><Trash2 size={10} /></button>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <button onClick={() => updateTypeMut.mutate({ name_cn: form.name_cn, name_en: form.name_en, description: form.description, property_schema: buildSchema() })} className="flex items-center gap-1 px-3 py-1.5 bg-black text-white rounded-lg text-sm"><Save size={12} /> 保存</button>
              <button onClick={() => setEditing(false)} className="px-3 py-1.5 border rounded-lg text-sm text-gray-500"><X size={12} /> 取消</button>
            </div>
          </div>
        ) : (
          <div>
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-gray-900">{type.name_cn}</h2>
                {type.name_en && <p className="text-sm text-gray-400 font-mono">{type.name_en}</p>}
              </div>
              <button onClick={startEdit} className="text-gray-400 hover:text-gray-600"><Pencil size={16} /></button>
            </div>
            {type.description && <p className="text-sm text-gray-500 mt-3">{type.description}</p>}
          </div>
        )}
      </div>

      {/* Property Schema */}
      <div className="bg-white border rounded-xl p-5">
        <h3 className="font-semibold text-sm text-gray-800 mb-3">属性字段</h3>
        {Object.keys(schema).length === 0 ? (
          <p className="text-sm text-gray-400">暂无属性定义</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {Object.entries(schema).map(([name, def]) => (
              <span key={name} className={`inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-mono ${
                def.type === 'number' ? 'bg-blue-50 text-blue-700' :
                def.type === 'string' ? 'bg-green-50 text-green-700' :
                def.type === 'boolean' ? 'bg-purple-50 text-purple-700' : 'bg-gray-50 text-gray-600'
              }`}>
                {name}<span className="opacity-50">:{def.type}{def.unit ? `(${def.unit})` : ''}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Instances */}
      <div className="bg-white border rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b">
          <h3 className="font-semibold text-sm text-gray-800">实体实例 ({typeInstances.length})</h3>
          <button onClick={openInstForm} className="px-3 py-1.5 border rounded-lg text-xs text-gray-600 hover:bg-gray-50 flex items-center gap-1"><Plus size={12} /> 新增</button>
        </div>
        <div>
          {typeInstances.length === 0 ? (
            <div className="px-5 py-6 text-center text-sm text-gray-400">暂无实体实例</div>
          ) : (
            typeInstances.map(oi => (
              <div key={oi.id} className="flex items-center px-5 py-2.5 border-t hover:bg-gray-50 group cursor-pointer"
                onClick={() => navigate(`/ontologies/${ontologyId}/types/${typeId}/instances/${oi.id}`)}>
                <Box size={14} className="text-gray-400 mr-2" />
                <span className="flex-1 text-sm text-gray-800">{oi.name_cn}</span>
                <div className="flex flex-wrap gap-1 mr-2">
                  {Object.entries(oi.properties || {}).slice(0, 4).map(([k, v]) => (
                    <span key={k} className="text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded font-mono">{k}={String(v)}</span>
                  ))}
                </div>
                <button onClick={(e) => { e.stopPropagation(); if (confirm(`删除"${oi.name_cn}"？`)) deleteInstMut.mutate(oi.id) }}
                  className="text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100"><Trash2 size={14} /></button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Rules */}
      <div className="bg-white border rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b">
          <div>
            <h3 className="font-semibold text-sm text-gray-800">规则 ({typeRules.length})</h3>
            <p className="text-xs text-gray-400 mt-0.5">本体层规则，适用于所有实体</p>
          </div>
          <button onClick={() => { setRuleEditor({}); setRuleForm({ name_cn: '', description: '', python_code: 'def check(context: dict) -> dict:\n    return {"passed": True, "message": "ok"}\n' }) }}
            className="px-3 py-1.5 border rounded-lg text-xs text-gray-600 hover:bg-gray-50 flex items-center gap-1"><Plus size={12} /> 新增规则</button>
        </div>
        <div>
          {typeRules.length === 0 ? (
            <div className="px-5 py-6 text-center text-sm text-gray-400">暂无规则</div>
          ) : (
            typeRules.map((r: any) => (
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
          <div>
            <h3 className="font-semibold text-sm text-gray-800">动作 ({typeActions.length})</h3>
            <p className="text-xs text-gray-400 mt-0.5">本体层动作，适用于所有实体</p>
          </div>
          <button onClick={() => { setActionEditor({}); setActionForm({ name_cn: '', description: '', python_code: 'def execute(context: dict) -> dict:\n    return {"status": "done"}\n' }) }}
            className="px-3 py-1.5 border rounded-lg text-xs text-gray-600 hover:bg-gray-50 flex items-center gap-1"><Plus size={12} /> 新增动作</button>
        </div>
        <div>
          {typeActions.length === 0 ? (
            <div className="px-5 py-6 text-center text-sm text-gray-400">暂无动作</div>
          ) : (
            typeActions.map((a: any) => (
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

      {/* Instance Create/Edit Modal */}
      {(showInstForm || editInstId) && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => { setShowInstForm(false); setEditInstId(null) }}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-xl max-h-[75vh] overflow-auto m-4" onClick={e => e.stopPropagation()}>
            <div className="p-5 space-y-4">
              <h3 className="font-semibold text-gray-800">{editInstId ? '编辑实体' : '新增实体'} — {type.name_cn}</h3>
              <input value={instForm.name_cn} onChange={e => setInstForm({ ...instForm, name_cn: e.target.value })} placeholder="实体中文名 *" className="w-full border rounded-lg px-3 py-2 text-sm" />
              <input value={instForm.name_en} onChange={e => setInstForm({ ...instForm, name_en: e.target.value })} placeholder="实体英文名" className="w-full border rounded-lg px-3 py-2 text-sm" />
              {Object.keys(schema).length > 0 && (
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(schema).map(([name, def]) => (
                    <div key={name}><label className="block text-[10px] text-gray-500 mb-0.5">{name}{def.unit ? ` (${def.unit})` : ''}</label>
                      {def.type === 'boolean' ? (
                        <select value={instProps[name] || ''} onChange={e => setInstProps({ ...instProps, [name]: e.target.value })} className="w-full border rounded px-2 py-1 text-xs"><option value="">—</option><option value="true">是</option><option value="false">否</option></select>
                      ) : def.type === 'number' ? (
                        <input type="number" value={instProps[name] || ''} onChange={e => setInstProps({ ...instProps, [name]: e.target.value })} className="w-full border rounded px-2 py-1 text-xs" />
                      ) : (
                        <input value={instProps[name] || ''} onChange={e => setInstProps({ ...instProps, [name]: e.target.value })} className="w-full border rounded px-2 py-1 text-xs" />
                      )}
                    </div>
                  ))}
                </div>
              )}
              <div className="flex gap-2 justify-end">
                {editInstId ? (
                  <button onClick={() => {
                    const props: any = {}
                    Object.entries(instProps).forEach(([k, v]) => {
                      const def = schema[k]
                      if (def?.type === 'number') { const n = parseFloat(v); if (!isNaN(n)) props[k] = n; else if (v) props[k] = v }
                      else if (v) props[k] = v
                    })
                    updateInstMut.mutate({ id: editInstId, data: { name_cn: instForm.name_cn, name_en: instForm.name_en, description: instForm.description, properties: props } })
                  }} disabled={!instForm.name_cn}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 更新</button>
                ) : (
                  <button onClick={() => {
                    const props: any = {}
                    Object.entries(instProps).forEach(([k, v]) => {
                      const def = schema[k]
                      if (def?.type === 'number') { const n = parseFloat(v); if (!isNaN(n)) props[k] = n; else if (v) props[k] = v }
                      else if (v) props[k] = v
                    })
                    createInstMut.mutate({ name_cn: instForm.name_cn, name_en: instForm.name_en, description: instForm.description, object_type_id: typeId, properties: props })
                  }} disabled={!instForm.name_cn}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 创建</button>
                )}
                <button onClick={() => { setShowInstForm(false); setEditInstId(null) }} className="px-4 py-2 border rounded-lg text-sm text-gray-500">取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
      {/* ── 规则编辑器弹窗 ── */}
      {ruleEditor && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setRuleEditor(null)}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-auto m-4" onClick={e => e.stopPropagation()}>
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between"><h3 className="font-semibold text-gray-800">{ruleEditor.editId ? '编辑规则' : '新增规则'}</h3><button onClick={() => setRuleEditor(null)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button></div>
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
                  <button onClick={() => updateRuleMut.mutate({ id: ruleEditor.editId!, data: ruleForm })} disabled={!ruleForm.name_cn}
                    className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 更新</button>
                ) : (
                  <button onClick={() => createRuleMut.mutate({ ...ruleForm, object_type_id: typeId })} disabled={!ruleForm.name_cn}
                    className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 创建</button>
                )}
                <button onClick={() => setRuleEditor(null)} className="px-4 py-2 border rounded-lg text-sm text-gray-500">取消</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── 动作编辑器弹窗 ── */}
      {actionEditor && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setActionEditor(null)}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-auto m-4" onClick={e => e.stopPropagation()}>
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between"><h3 className="font-semibold text-gray-800">{actionEditor.editId ? '编辑动作' : '新增动作'}</h3><button onClick={() => setActionEditor(null)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button></div>
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
                  <button onClick={() => updateActionMut.mutate({ id: actionEditor.editId!, data: actionForm })} disabled={!actionForm.name_cn}
                    className="px-4 py-2 bg-amber-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 更新</button>
                ) : (
                  <button onClick={() => createActionMut.mutate({ ...actionForm, object_type_id: typeId })} disabled={!actionForm.name_cn}
                    className="px-4 py-2 bg-amber-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 创建</button>
                )}
                <button onClick={() => setActionEditor(null)} className="px-4 py-2 border rounded-lg text-sm text-gray-500">取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
