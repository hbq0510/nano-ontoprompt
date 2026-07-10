import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ontologyApi } from '@/api/ontologies'
import { Search, Box, Plus, Trash2, Pencil, X, Save, ChevronDown, ChevronUp } from 'lucide-react'
import type { ObjectInstance, ObjectType } from '@/types/ontology'

export default function ObjectInstancesTab({ ontologyId }: { ontologyId: string }) {
  const [searchQ, setSearchQ] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [form, setForm] = useState({ name_cn: '', name_en: '', description: '', object_type_id: '' })
  const [propValues, setPropValues] = useState<Record<string, string>>({})
  const qc = useQueryClient()

  const { data: instances = [], isLoading } = useQuery({
    queryKey: ['object-instances', ontologyId],
    queryFn: () => ontologyApi.listInstances(ontologyId) as Promise<ObjectInstance[]>,
  })
  const { data: types = [] } = useQuery({
    queryKey: ['object-types', ontologyId],
    queryFn: () => ontologyApi.listObjectTypes(ontologyId) as Promise<ObjectType[]>,
  })

  const createMut = useMutation({
    mutationFn: (data: any) => ontologyApi.createInstance(ontologyId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-instances', ontologyId] }); setShowCreate(false); resetForm() },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => ontologyApi.updateInstance(ontologyId, id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-instances', ontologyId] }); setEditId(null) },
  })
  const deleteMut = useMutation({
    mutationFn: (id: string) => ontologyApi.deleteInstance(ontologyId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['object-instances', ontologyId] }),
  })

  const typeMap = useMemo(() => {
    const m: Record<string, ObjectType> = {}
    ;(types as ObjectType[]).forEach(t => { m[t.id] = t })
    return m
  }, [types])

  // 当前选中 ObjectType 的 property_schema
  const selectedTypeSchema = useMemo(() => {
    if (!form.object_type_id) return {}
    const ot = typeMap[form.object_type_id]
    return (ot?.property_schema || {}) as Record<string, { type: string; unit?: string }>
  }, [form.object_type_id, typeMap])

  const groups = useMemo(() => {
    const g: Record<string, ObjectInstance[]> = {}
    ;(instances as ObjectInstance[]).forEach(i => {
      const key = i.object_type_id
      if (!g[key]) g[key] = []
      g[key].push(i)
    })
    return g
  }, [instances])

  const filtered = useMemo(() => {
    const q = searchQ.trim().toLowerCase()
    return (instances as ObjectInstance[]).filter(i => {
      const matchQ = !q || i.name_cn?.toLowerCase().includes(q) || i.name_en?.toLowerCase().includes(q)
      const matchType = !typeFilter || i.object_type_id === typeFilter
      return matchQ && matchType
    })
  }, [instances, searchQ, typeFilter])

  function resetForm() {
    setForm({ name_cn: '', name_en: '', description: '', object_type_id: '' })
    setPropValues({})
  }
  function startEdit(inst: ObjectInstance) {
    setEditId(inst.id)
    setForm({ name_cn: inst.name_cn, name_en: inst.name_en || '', description: inst.description || '',
      object_type_id: inst.object_type_id })
    const vals: Record<string, string> = {}
    Object.entries(inst.properties || {}).forEach(([k, v]) => { vals[k] = String(v ?? '') })
    setPropValues(vals)
  }
  function buildProperties(): Record<string, any> {
    const props: Record<string, any> = {}
    Object.entries(propValues).forEach(([k, v]) => {
      const schema = selectedTypeSchema[k]
      if (schema?.type === 'number') {
        const num = parseFloat(v)
        if (!isNaN(num)) props[k] = num
        else if (v) props[k] = v
      } else if (v) {
        props[k] = v
      }
    })
    return props
  }
  function toggleExpand(id: string) {
    const next = new Set(expanded)
    next.has(id) ? next.delete(id) : next.add(id)
    setExpanded(next)
  }

  if (isLoading) return <div className="p-6 text-gray-400">加载中...</div>

  return (
    <div className="space-y-4">
      {/* 类型统计 */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
        {Object.entries(groups).map(([typeId, group]) => {
          const ot = typeMap[typeId]
          return (
            <button key={typeId} onClick={() => setTypeFilter(typeId === typeFilter ? '' : typeId)}
              className={`text-left p-3 rounded-xl border transition-colors ${
                typeFilter === typeId ? 'bg-blue-50 border-blue-300' : 'bg-white border-gray-200 hover:bg-gray-50'}`}>
              <p className="text-xs text-gray-400 truncate">{ot?.name_cn || typeId.slice(0, 8)}</p>
              <p className="text-lg font-bold text-gray-800">{group.length}</p>
              <p className="text-[10px] text-gray-400">个实例</p>
            </button>
          )
        })}
      </div>

      {/* 操作栏 */}
      <div className="flex gap-2 items-center">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <input value={searchQ} onChange={e => setSearchQ(e.target.value)}
            placeholder="搜索实例名..." className="w-full border rounded-lg pl-8 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black" />
        </div>
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
          className="border rounded-lg px-3 py-2 text-sm text-gray-600">
          <option value="">全部类型</option>
          {Object.keys(groups).map(tid => {
            const ot = typeMap[tid]
            return <option key={tid} value={tid}>{ot?.name_cn || tid.slice(0, 8)} ({groups[tid].length})</option>
          })}
        </select>
        <button onClick={() => { setShowCreate(true); resetForm() }}
          className="flex items-center gap-1 px-3 py-2 bg-black text-white rounded-lg text-sm">
          <Plus size={14} /> 新建实例
        </button>
      </div>

      {/* 新建表单 */}
      {showCreate && (
        <div className="bg-white border rounded-xl p-4 space-y-3">
          <h4 className="text-sm font-semibold">新建对象实例</h4>
          <select value={form.object_type_id} onChange={e => { setForm({ ...form, object_type_id: e.target.value }); setPropValues({}) }}
            className="w-full border rounded-lg px-3 py-2 text-sm">
            <option value="">选择所属类型 *</option>
            {(types as ObjectType[]).map(ot => (
              <option key={ot.id} value={ot.id}>{ot.name_cn || ot.id.slice(0, 8)}</option>
            ))}
          </select>
          <input value={form.name_cn} onChange={e => setForm({ ...form, name_cn: e.target.value })}
            placeholder="中文名 *" className="w-full border rounded-lg px-3 py-2 text-sm" />
          <input value={form.name_en} onChange={e => setForm({ ...form, name_en: e.target.value })}
            placeholder="英文名" className="w-full border rounded-lg px-3 py-2 text-sm" />
          <input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
            placeholder="描述" className="w-full border rounded-lg px-3 py-2 text-sm" />

          {/* 根据 property_schema 动态生成属性字段 */}
          {Object.keys(selectedTypeSchema).length > 0 && (
            <div className="border-t pt-3">
              <p className="text-xs font-medium text-gray-500 mb-2">属性值（根据 {typeMap[form.object_type_id]?.name_cn} 的字段定义）</p>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(selectedTypeSchema).map(([name, schema]) => (
                  <div key={name}>
                    <label className="block text-[10px] text-gray-500 mb-0.5">
                      {name}{schema.unit ? ` (${schema.unit})` : ''}
                      <span className="text-gray-300"> — {schema.type}</span>
                    </label>
                    {schema.type === 'boolean' ? (
                      <select value={propValues[name] || ''} onChange={e => setPropValues({ ...propValues, [name]: e.target.value })}
                        className="w-full border rounded px-2 py-1.5 text-xs">
                        <option value="">—</option>
                        <option value="true">是</option>
                        <option value="false">否</option>
                      </select>
                    ) : schema.type === 'number' ? (
                      <input type="number" value={propValues[name] || ''} onChange={e => setPropValues({ ...propValues, [name]: e.target.value })}
                        placeholder="输入数值" className="w-full border rounded px-2 py-1.5 text-xs" />
                    ) : (
                      <input value={propValues[name] || ''} onChange={e => setPropValues({ ...propValues, [name]: e.target.value })}
                        placeholder="输入文本" className="w-full border rounded px-2 py-1.5 text-xs" />
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {form.object_type_id && Object.keys(selectedTypeSchema).length === 0 && (
            <p className="text-xs text-amber-600">该类型未定义 property_schema，实例将不带属性。</p>
          )}

          <div className="flex gap-2">
            <button onClick={() => createMut.mutate({
              name_cn: form.name_cn, name_en: form.name_en,
              description: form.description, object_type_id: form.object_type_id,
              properties: buildProperties(),
            })} disabled={!form.name_cn || !form.object_type_id}
              className="flex items-center gap-1 px-3 py-1.5 bg-black text-white rounded-lg text-sm disabled:opacity-40"><Save size={12} /> 保存</button>
            <button onClick={() => setShowCreate(false)}
              className="px-3 py-1.5 border rounded-lg text-sm text-gray-500"><X size={12} /> 取消</button>
          </div>
        </div>
      )}

      {/* 实例表格 */}
      <div className="bg-white border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-2.5 text-left text-xs text-gray-500 font-medium w-8"></th>
              <th className="px-4 py-2.5 text-left text-xs text-gray-500 font-medium">实例名</th>
              <th className="px-4 py-2.5 text-left text-xs text-gray-500 font-medium">所属类型</th>
              <th className="px-4 py-2.5 text-left text-xs text-gray-500 font-medium">属性值</th>
              <th className="px-4 py-2.5 text-right text-xs text-gray-500 font-medium w-16">操作</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 100).map((inst: ObjectInstance) => {
              const ot = typeMap[inst.object_type_id]
              const propEntries = Object.entries(inst.properties || {})
              const isExpanded = expanded.has(inst.id)
              const displayProps = isExpanded ? propEntries : propEntries.slice(0, 5)
              const isEditing = editId === inst.id

              if (isEditing) {
                const editSchema = (typeMap[inst.object_type_id]?.property_schema || {}) as Record<string, { type: string; unit?: string }>
                return (
                  <tr key={inst.id} className="border-t bg-blue-50/30">
                    <td colSpan={5} className="px-4 py-3">
                      <div className="space-y-2">
                        <h4 className="text-xs font-semibold">编辑：{inst.name_cn}</h4>
                        <input value={form.name_cn} onChange={e => setForm({ ...form, name_cn: e.target.value })}
                          placeholder="中文名" className="w-full border rounded px-2 py-1 text-sm" />
                        {/* 动态属性编辑 */}
                        {Object.keys(editSchema).length > 0 && (
                          <div className="grid grid-cols-2 gap-2">
                            {Object.entries(editSchema).map(([name, schema]) => (
                              <div key={name}>
                                <label className="block text-[10px] text-gray-500 mb-0.5">{name}{schema.unit ? ` (${schema.unit})` : ''}</label>
                                {schema.type === 'boolean' ? (
                                  <select value={propValues[name] || ''} onChange={e => setPropValues({ ...propValues, [name]: e.target.value })}
                                    className="w-full border rounded px-2 py-1 text-xs">
                                    <option value="">—</option>
                                    <option value="true">是</option>
                                    <option value="false">否</option>
                                  </select>
                                ) : schema.type === 'number' ? (
                                  <input type="number" value={propValues[name] || ''} onChange={e => setPropValues({ ...propValues, [name]: e.target.value })}
                                    className="w-full border rounded px-2 py-1 text-xs" />
                                ) : (
                                  <input value={propValues[name] || ''} onChange={e => setPropValues({ ...propValues, [name]: e.target.value })}
                                    className="w-full border rounded px-2 py-1 text-xs" />
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                        <div className="flex gap-2">
                          <button onClick={() => updateMut.mutate({ id: inst.id, data: {
                            name_cn: form.name_cn,
                            properties: buildProperties(),
                          }})}
                            className="flex items-center gap-1 px-2 py-1 bg-black text-white rounded text-xs"><Save size={10} /> 更新</button>
                          <button onClick={() => setEditId(null)}
                            className="px-2 py-1 border rounded text-xs text-gray-500"><X size={10} /> 取消</button>
                        </div>
                      </div>
                    </td>
                  </tr>
                )
              }

              return (
                <tr key={inst.id} className="border-t hover:bg-gray-50 transition-colors align-top">
                  <td className="px-3 py-2">
                    {propEntries.length > 5 && (
                      <button onClick={() => toggleExpand(inst.id)}
                        className="text-gray-400 hover:text-gray-600">
                        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <span className="font-medium text-gray-800 text-xs">{inst.name_cn}</span>
                    {inst.name_en && <span className="text-[10px] text-gray-400 ml-1 font-mono">{inst.name_en}</span>}
                  </td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1 text-[10px] text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded-full">
                      <Box size={9} />{ot?.name_cn || inst.object_type_id.slice(0, 8)}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {displayProps.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {displayProps.map(([k, v]) => (
                          <span key={k} className="text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded font-mono max-w-[200px] truncate">
                            {k}={String(v)}
                          </span>
                        ))}
                        {!isExpanded && propEntries.length > 5 && (
                          <span className="text-[10px] text-gray-400">+{propEntries.length - 5} 更多</span>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-2 py-2 text-right">
                    <div className="flex items-center gap-1 justify-end">
                      <button onClick={() => startEdit(inst)}
                        className="text-gray-300 hover:text-gray-600"><Pencil size={11} /></button>
                      <button onClick={() => { if (confirm(`删除实例 "${inst.name_cn}"？`)) deleteMut.mutate(inst.id) }}
                        className="text-gray-300 hover:text-red-500"><Trash2 size={11} /></button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="p-8 text-center text-gray-400 text-sm">暂无实例数据</div>
        )}
      </div>
    </div>
  )
}
