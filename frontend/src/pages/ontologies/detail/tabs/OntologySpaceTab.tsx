import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ontologyApi } from '@/api/ontologies'
import { ChevronRight, ChevronDown, Plus, Trash2, Pencil, X, Save, GripVertical, Box, Layers } from 'lucide-react'
import type { ObjectType, ObjectInstance } from '@/types/ontology'

interface SchemaField { key: string; name: string; type: string; unit: string }

export default function OntologySpaceTab({ ontologyId }: { ontologyId: string }) {
  const qc = useQueryClient()

  const { data: types = [], isLoading: typesLoading } = useQuery({
    queryKey: ['object-types', ontologyId],
    queryFn: () => ontologyApi.listObjectTypes(ontologyId) as Promise<ObjectType[]>,
  })
  const { data: instances = [] } = useQuery({
    queryKey: ['object-instances', ontologyId],
    queryFn: () => ontologyApi.listInstances(ontologyId) as Promise<ObjectInstance[]>,
  })

  // ── 按 ObjectType 分组实例 ──
  const instancesByType = useMemo(() => {
    const map: Record<string, ObjectInstance[]> = {}
    ;(instances as ObjectInstance[]).forEach(i => {
      const tid = i.object_type_id
      if (!map[tid]) map[tid] = []
      map[tid].push(i)
    })
    return map
  }, [instances])

  // ── 展开/折叠状态 ──
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set())

  // ── 新建类型表单 ──
  const [showCreateType, setShowCreateType] = useState(false)
  const [typeForm, setTypeForm] = useState({ name_cn: '', name_en: '', description: '' })
  const [typeFields, setTypeFields] = useState<SchemaField[]>([])

  // ── 编辑类型 ──
  const [editTypeId, setEditTypeId] = useState<string | null>(null)
  const [editTypeFields, setEditTypeFields] = useState<SchemaField[]>([])

  // ── 新建实例表单 (key = typeId) ──
  const [showCreateInst, setShowCreateInst] = useState<string | null>(null)
  const [instForm, setInstForm] = useState({ name_cn: '', name_en: '', description: '' })
  const [instPropValues, setInstPropValues] = useState<Record<string, string>>({})

  // ── 编辑实例 ──
  const [editInstId, setEditInstId] = useState<string | null>(null)
  const [editInstForm, setEditInstForm] = useState({ name_cn: '', name_en: '', description: '' })
  const [editInstProps, setEditInstProps] = useState<Record<string, string>>({})

  // ── Mutations ──
  const createTypeMut = useMutation({
    mutationFn: (data: any) => ontologyApi.createObjectType(ontologyId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-types', ontologyId] }); setShowCreateType(false); resetTypeForm() },
  })
  const updateTypeMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => ontologyApi.updateObjectType(ontologyId, id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-types', ontologyId] }); setEditTypeId(null) },
  })
  const deleteTypeMut = useMutation({
    mutationFn: (id: string) => ontologyApi.deleteObjectType(ontologyId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['object-types', ontologyId] }),
  })

  const createInstMut = useMutation({
    mutationFn: (data: any) => ontologyApi.createInstance(ontologyId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-instances', ontologyId] }); setShowCreateInst(null); resetInstForm() },
  })
  const updateInstMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => ontologyApi.updateInstance(ontologyId, id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-instances', ontologyId] }); setEditInstId(null) },
  })
  const deleteInstMut = useMutation({
    mutationFn: (id: string) => ontologyApi.deleteInstance(ontologyId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['object-instances', ontologyId] }),
  })

  // ── Helpers ──
  function resetTypeForm() { setTypeForm({ name_cn: '', name_en: '', description: '' }); setTypeFields([]) }
  function resetInstForm() { setInstForm({ name_cn: '', name_en: '', description: '' }); setInstPropValues({}) }

  function startEditType(ot: ObjectType) {
    setEditTypeId(ot.id)
    setTypeForm({ name_cn: ot.name_cn, name_en: ot.name_en || '', description: ot.description || '' })
    const fields: SchemaField[] = []
    let idx = 0
    Object.entries(ot.property_schema || {}).forEach(([name, def]) => {
      fields.push({ key: `ef-${idx++}`, name, type: def.type || 'string', unit: def.unit || '' })
    })
    setEditTypeFields(fields)
  }
  function startEditInst(oi: ObjectInstance) {
    setEditInstId(oi.id)
    setEditInstForm({ name_cn: oi.name_cn, name_en: oi.name_en || '', description: oi.description || '' })
    const vals: Record<string, string> = {}
    Object.entries(oi.properties || {}).forEach(([k, v]) => { vals[k] = String(v ?? '') })
    setEditInstProps(vals)
  }
  function buildTypeSchema(fields: SchemaField[]): Record<string, { type: string; unit?: string }> {
    const schema: Record<string, { type: string; unit?: string }> = {}
    fields.forEach(f => { if (f.name.trim()) schema[f.name.trim()] = { type: f.type, unit: f.unit || undefined } })
    return schema
  }
  function buildInstProps(values: Record<string, string>, schema: Record<string, { type: string; unit?: string }>): Record<string, any> {
    const props: Record<string, any> = {}
    Object.entries(values).forEach(([k, v]) => {
      if (schema[k]?.type === 'number') { const n = parseFloat(v); if (!isNaN(n)) props[k] = n; else if (v) props[k] = v }
      else if (v) props[k] = v
    })
    return props
  }
  function addTypeField(target: 'create' | 'edit') {
    const adder = target === 'create' ? setTypeFields : setEditTypeFields
    adder(prev => [...prev, { key: `f-${Date.now()}`, name: '', type: 'string', unit: '' }])
  }
  function updateTypeField(target: 'create' | 'edit', key: string, patch: Partial<SchemaField>) {
    const setter = target === 'create' ? setTypeFields : setEditTypeFields
    setter(prev => prev.map(f => f.key === key ? { ...f, ...patch } : f))
  }
  function removeTypeField(target: 'create' | 'edit', key: string) {
    const setter = target === 'create' ? setTypeFields : setEditTypeFields
    setter(prev => prev.filter(f => f.key !== key))
  }
  function getTypeSchema(typeId: string): Record<string, { type: string; unit?: string }> {
    const ot = (types as ObjectType[]).find(t => t.id === typeId)
    return (ot?.property_schema || {}) as Record<string, { type: string; unit?: string }>
  }

  if (typesLoading) return <div className="p-6 text-gray-400">加载中...</div>

  // ── 渲染属性字段编辑器 ──
  function renderFieldEditor(fields: SchemaField[], target: 'create' | 'edit') {
    return (
      <div className="border-t pt-3">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-medium text-gray-500">属性字段定义</p>
          <button onClick={() => addTypeField(target)}
            className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800">
            <Plus size={12} /> 添加字段
          </button>
        </div>
        {fields.length === 0 && <p className="text-xs text-gray-400 py-2">暂无字段</p>}
        <div className="space-y-2">
          {fields.map(f => (
            <div key={f.key} className="flex items-center gap-2">
              <GripVertical size={12} className="text-gray-300 flex-shrink-0" />
              <input value={f.name} onChange={e => updateTypeField(target, f.key, { name: e.target.value })}
                placeholder="字段名" className="flex-1 border rounded px-2 py-1.5 text-xs" />
              <select value={f.type} onChange={e => updateTypeField(target, f.key, { type: e.target.value })}
                className="border rounded px-2 py-1.5 text-xs w-20">
                <option value="string">文本</option>
                <option value="number">数字</option>
                <option value="boolean">布尔</option>
              </select>
              <input value={f.unit} onChange={e => updateTypeField(target, f.key, { unit: e.target.value })}
                placeholder="单位" className="border rounded px-2 py-1.5 text-xs w-16" />
              <button onClick={() => removeTypeField(target, f.key)} className="text-gray-300 hover:text-red-500"><Trash2 size={12} /></button>
            </div>
          ))}
        </div>
      </div>
    )
  }

  // ── 渲染实例属性输入 ──
  function renderInstPropInputs(typeId: string, values: Record<string, string>, setter: (v: Record<string, string>) => void) {
    const schema = getTypeSchema(typeId)
    const entries = Object.entries(schema)
    if (entries.length === 0) return null
    return (
      <div className="grid grid-cols-2 gap-2 mt-2">
        {entries.map(([name, def]) => (
          <div key={name}>
            <label className="block text-[10px] text-gray-500 mb-0.5">{name}{def.unit ? ` (${def.unit})` : ''}</label>
            {def.type === 'boolean' ? (
              <select value={values[name] || ''} onChange={e => setter({ ...values, [name]: e.target.value })}
                className="w-full border rounded px-2 py-1 text-xs">
                <option value="">—</option>
                <option value="true">是</option>
                <option value="false">否</option>
              </select>
            ) : def.type === 'number' ? (
              <input type="number" value={values[name] || ''} onChange={e => setter({ ...values, [name]: e.target.value })}
                className="w-full border rounded px-2 py-1 text-xs" />
            ) : (
              <input value={values[name] || ''} onChange={e => setter({ ...values, [name]: e.target.value })}
                className="w-full border rounded px-2 py-1 text-xs" />
            )}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* ── 新建类型按钮 ── */}
      <div className="flex items-center gap-2">
        <button onClick={() => { setShowCreateType(true); resetTypeForm() }}
          className="flex items-center gap-1 px-3 py-2 bg-black text-white rounded-lg text-sm">
          <Plus size={14} /> 新建类型
        </button>
        <span className="text-xs text-gray-400">{(types as ObjectType[]).length} 个类型 · {(instances as ObjectInstance[]).length} 个实例</span>
      </div>

      {/* ── 新建类型表单 ── */}
      {showCreateType && (
        <div className="bg-white border rounded-xl p-4 space-y-3">
          <h4 className="text-sm font-semibold">新建对象类型</h4>
          <input value={typeForm.name_cn} onChange={e => setTypeForm({ ...typeForm, name_cn: e.target.value })}
            placeholder="中文名 *" className="w-full border rounded-lg px-3 py-2 text-sm" />
          <input value={typeForm.name_en} onChange={e => setTypeForm({ ...typeForm, name_en: e.target.value })}
            placeholder="英文名" className="w-full border rounded-lg px-3 py-2 text-sm" />
          <input value={typeForm.description} onChange={e => setTypeForm({ ...typeForm, description: e.target.value })}
            placeholder="描述" className="w-full border rounded-lg px-3 py-2 text-sm" />
          {renderFieldEditor(typeFields, 'create')}
          <div className="flex gap-2">
            <button onClick={() => createTypeMut.mutate({
              name_cn: typeForm.name_cn, name_en: typeForm.name_en,
              description: typeForm.description, property_schema: buildTypeSchema(typeFields),
            })} disabled={!typeForm.name_cn}
              className="flex items-center gap-1 px-3 py-1.5 bg-black text-white rounded-lg text-sm disabled:opacity-40"><Save size={12} /> 保存</button>
            <button onClick={() => setShowCreateType(false)} className="px-3 py-1.5 border rounded-lg text-sm text-gray-500"><X size={12} /> 取消</button>
          </div>
        </div>
      )}

      {/* ── 树状结构 ── */}
      {(types as ObjectType[]).map(ot => {
        const otInstances = instancesByType[ot.id] || []
        const isExpanded = expandedTypes.has(ot.id)
        const isEditingType = editTypeId === ot.id
        const isCreatingInst = showCreateInst === ot.id

        if (isEditingType) {
          return (
            <div key={ot.id} className="bg-white border rounded-xl p-4 space-y-3 bg-blue-50/30">
              <h4 className="text-sm font-semibold">编辑类型：{ot.name_cn}</h4>
              <input value={typeForm.name_cn} onChange={e => setTypeForm({ ...typeForm, name_cn: e.target.value })}
                placeholder="中文名" className="w-full border rounded-lg px-3 py-2 text-sm" />
              <input value={typeForm.name_en} onChange={e => setTypeForm({ ...typeForm, name_en: e.target.value })}
                placeholder="英文名" className="w-full border rounded-lg px-3 py-2 text-sm" />
              <input value={typeForm.description} onChange={e => setTypeForm({ ...typeForm, description: e.target.value })}
                placeholder="描述" className="w-full border rounded-lg px-3 py-2 text-sm" />
              {renderFieldEditor(editTypeFields, 'edit')}
              <div className="flex gap-2">
                <button onClick={() => updateTypeMut.mutate({ id: ot.id, data: {
                  name_cn: typeForm.name_cn, name_en: typeForm.name_en,
                  description: typeForm.description, property_schema: buildTypeSchema(editTypeFields),
                }})} className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm"><Save size={12} /> 更新</button>
                <button onClick={() => setEditTypeId(null)} className="px-3 py-1.5 border rounded-lg text-sm text-gray-500"><X size={12} /> 取消</button>
              </div>
            </div>
          )
        }

        return (
          <div key={ot.id} className="bg-white border rounded-xl overflow-hidden">
            {/* ── 类型行 ── */}
            <div className="flex items-center px-4 py-3 hover:bg-gray-50 cursor-pointer"
              onClick={() => {
                const next = new Set(expandedTypes)
                isExpanded ? next.delete(ot.id) : next.add(ot.id)
                setExpandedTypes(next)
              }}>
              <div className="flex items-center gap-2 flex-1 min-w-0">
                {isExpanded ? <ChevronDown size={16} className="text-gray-400 flex-shrink-0" /> : <ChevronRight size={16} className="text-gray-400 flex-shrink-0" />}
                <Layers size={16} className="text-gray-400 flex-shrink-0" />
                <span className="font-semibold text-gray-800 text-sm truncate">{ot.name_cn}</span>
                {ot.name_en && <span className="text-xs text-gray-400 font-mono truncate">{ot.name_en}</span>}
                <span className="text-xs text-gray-400 ml-2 flex-shrink-0">({otInstances.length} 个实例)</span>
                {/* 属性标签 */}
                {Object.entries(ot.property_schema || {}).slice(0, 3).map(([name, def]) => (
                  <span key={name} className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full flex-shrink-0 hidden sm:inline">
                    {name}{def.unit ? `(${def.unit})` : ''}
                  </span>
                ))}
                {Object.keys(ot.property_schema || {}).length > 3 && (
                  <span className="text-[10px] text-gray-400 flex-shrink-0 hidden sm:inline">+{Object.keys(ot.property_schema || {}).length - 3}</span>
                )}
              </div>
              <div className="flex items-center gap-1 flex-shrink-0" onClick={e => e.stopPropagation()}>
                <button onClick={() => { setShowCreateInst(ot.id); resetInstForm() }}
                  className="flex items-center gap-0.5 text-[10px] text-blue-600 hover:text-blue-800 px-1.5 py-0.5 rounded hover:bg-blue-50">
                  <Plus size={10} /> 实例
                </button>
                <button onClick={() => startEditType(ot)}
                  className="text-gray-300 hover:text-gray-600 p-1"><Pencil size={12} /></button>
                <button onClick={() => { if (confirm(`删除类型"${ot.name_cn}"及其实例？`)) deleteTypeMut.mutate(ot.id) }}
                  className="text-gray-300 hover:text-red-500 p-1"><Trash2 size={12} /></button>
              </div>
            </div>

            {/* ── 新建实例表单 ── */}
            {isCreatingInst && (
              <div className="border-t px-4 py-3 bg-blue-50/20 space-y-2">
                <h4 className="text-xs font-semibold">新建实例 — {ot.name_cn}</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <input value={instForm.name_cn} onChange={e => setInstForm({ ...instForm, name_cn: e.target.value })}
                    placeholder="实例中文名 *" className="border rounded px-2 py-1.5 text-xs" />
                  <input value={instForm.name_en} onChange={e => setInstForm({ ...instForm, name_en: e.target.value })}
                    placeholder="实例英文名" className="border rounded px-2 py-1.5 text-xs" />
                </div>
                <input value={instForm.description} onChange={e => setInstForm({ ...instForm, description: e.target.value })}
                  placeholder="描述" className="border rounded px-2 py-1.5 text-xs w-full" />
                {renderInstPropInputs(ot.id, instPropValues, setInstPropValues)}
                <div className="flex gap-2">
                  <button onClick={() => createInstMut.mutate({
                    name_cn: instForm.name_cn, name_en: instForm.name_en,
                    description: instForm.description, object_type_id: ot.id,
                    properties: buildInstProps(instPropValues, getTypeSchema(ot.id)),
                  })} disabled={!instForm.name_cn}
                    className="flex items-center gap-1 px-3 py-1.5 bg-black text-white rounded-lg text-xs disabled:opacity-40"><Save size={10} /> 保存</button>
                  <button onClick={() => setShowCreateInst(null)} className="px-3 py-1.5 border rounded-lg text-xs text-gray-500"><X size={10} /> 取消</button>
                </div>
              </div>
            )}

            {/* ── 实例列表 ── */}
            {isExpanded && (
              <div className="border-t">
                {otInstances.length === 0 && !isCreatingInst && (
                  <div className="px-4 py-4 text-xs text-gray-400 text-center">暂无实例，点击 [+ 实例] 创建</div>
                )}
                {otInstances.map(oi => {
                  const isEditingInst = editInstId === oi.id
                  if (isEditingInst) {
                    return (
                      <div key={oi.id} className="px-4 py-3 bg-yellow-50/30 border-t space-y-2">
                        <h4 className="text-xs font-semibold">编辑实例：{oi.name_cn}</h4>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <input value={editInstForm.name_cn} onChange={e => setEditInstForm({ ...editInstForm, name_cn: e.target.value })}
                            placeholder="实例中文名" className="border rounded px-2 py-1.5 text-xs" />
                          <input value={editInstForm.name_en} onChange={e => setEditInstForm({ ...editInstForm, name_en: e.target.value })}
                            placeholder="实例英文名" className="border rounded px-2 py-1.5 text-xs" />
                        </div>
                        {renderInstPropInputs(oi.object_type_id, editInstProps, setEditInstProps)}
                        <div className="flex gap-2">
                          <button onClick={() => updateInstMut.mutate({ id: oi.id, data: {
                            name_cn: editInstForm.name_cn, name_en: editInstForm.name_en,
                            description: editInstForm.description,
                            properties: buildInstProps(editInstProps, getTypeSchema(oi.object_type_id)),
                          }})} className="flex items-center gap-1 px-2 py-1 bg-black text-white rounded text-xs"><Save size={10} /> 更新</button>
                          <button onClick={() => setEditInstId(null)} className="px-2 py-1 border rounded text-xs text-gray-500"><X size={10} /> 取消</button>
                        </div>
                      </div>
                    )
                  }
                  return (
                    <div key={oi.id} className="flex items-center px-4 py-2 border-t hover:bg-gray-50">
                      <div className="w-5 flex-shrink-0" />
                      <Box size={12} className="text-gray-400 flex-shrink-0 mr-2" />
                      <span className="text-xs font-medium text-gray-700 w-32 flex-shrink-0 truncate">{oi.name_cn}</span>
                      <div className="flex flex-wrap gap-1 flex-1 min-w-0">
                        {Object.entries(oi.properties || {}).slice(0, 4).map(([k, v]) => (
                          <span key={k} className="text-[10px] bg-gray-100 text-gray-600 px-1 py-0.5 rounded font-mono truncate max-w-[150px]">
                            {k}={String(v)}
                          </span>
                        ))}
                        {Object.keys(oi.properties || {}).length > 4 && (
                          <span className="text-[10px] text-gray-400">+{Object.keys(oi.properties || {}).length - 4}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-0.5 flex-shrink-0">
                        <button onClick={() => startEditInst(oi)} className="text-gray-300 hover:text-gray-600 p-1"><Pencil size={10} /></button>
                        <button onClick={() => { if (confirm(`删除实例"${oi.name_cn}"？`)) deleteInstMut.mutate(oi.id) }}
                          className="text-gray-300 hover:text-red-500 p-1"><Trash2 size={10} /></button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
