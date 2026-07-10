import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ontologyApi } from '@/api/ontologies'
import { Search, Layers, Plus, Trash2, Pencil, X, Save, GripVertical } from 'lucide-react'
import type { ObjectType } from '@/types/ontology'

interface SchemaField { key: string; name: string; type: string; unit: string }

export default function ObjectTypesTab({ ontologyId }: { ontologyId: string }) {
  const [searchQ, setSearchQ] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [form, setForm] = useState({ name_cn: '', name_en: '', description: '' })
  const [schemaFields, setSchemaFields] = useState<SchemaField[]>([])

  const qc = useQueryClient()

  const { data: types = [], isLoading } = useQuery({
    queryKey: ['object-types', ontologyId],
    queryFn: () => ontologyApi.listObjectTypes(ontologyId) as Promise<ObjectType[]>,
  })

  const { data: interfaces = [] } = useQuery({
    queryKey: ['interfaces', ontologyId],
    queryFn: () => ontologyApi.listInterfaces(ontologyId) as any,
  })

  const createMut = useMutation({
    mutationFn: (data: any) => ontologyApi.createObjectType(ontologyId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-types', ontologyId] }); setShowCreate(false); resetForm() },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => ontologyApi.updateObjectType(ontologyId, id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['object-types', ontologyId] }); setEditId(null) },
  })
  const deleteMut = useMutation({
    mutationFn: (id: string) => ontologyApi.deleteObjectType(ontologyId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['object-types', ontologyId] }),
  })

  const ifaceMap = useMemo(() => {
    const m: Record<string, string> = {}
    ;(interfaces as any[]).forEach((i: any) => { m[i.id] = i.name_cn })
    return m
  }, [interfaces])

  const filtered = useMemo(() => {
    const q = searchQ.trim().toLowerCase()
    return (types as ObjectType[]).filter(t =>
      !q || t.name_cn?.toLowerCase().includes(q) || t.name_en?.toLowerCase().includes(q)
    )
  }, [types, searchQ])

  function resetForm() {
    setForm({ name_cn: '', name_en: '', description: '' })
    setSchemaFields([])
  }

  function startEdit(ot: ObjectType) {
    setEditId(ot.id)
    setForm({ name_cn: ot.name_cn, name_en: ot.name_en || '', description: ot.description || '' })
    const fields: SchemaField[] = []
    let idx = 0
    Object.entries(ot.property_schema || {}).forEach(([name, def]) => {
      fields.push({ key: `f-${idx++}`, name, type: def.type || 'string', unit: def.unit || '' })
    })
    setSchemaFields(fields)
  }

  function buildPropertySchema(): Record<string, { type: string; unit?: string }> {
    const schema: Record<string, { type: string; unit?: string }> = {}
    schemaFields.forEach(f => {
      if (f.name.trim()) {
        schema[f.name.trim()] = { type: f.type, unit: f.unit || undefined }
      }
    })
    return schema
  }

  function addField() {
    setSchemaFields(prev => [...prev, { key: `f-${Date.now()}`, name: '', type: 'string', unit: '' }])
  }
  function updateField(key: string, patch: Partial<SchemaField>) {
    setSchemaFields(prev => prev.map(f => f.key === key ? { ...f, ...patch } : f))
  }
  function removeField(key: string) {
    setSchemaFields(prev => prev.filter(f => f.key !== key))
  }

  if (isLoading) return <div className="p-6 text-gray-400">加载中...</div>

  return (
    <div className="space-y-4">
      <div className="flex gap-2 items-center">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <input value={searchQ} onChange={e => setSearchQ(e.target.value)}
            placeholder="搜索类型名..."
            className="w-full border rounded-lg pl-8 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black" />
        </div>
        <button onClick={() => { setShowCreate(true); resetForm() }}
          className="flex items-center gap-1 px-3 py-2 bg-black text-white rounded-lg text-sm">
          <Plus size={14} /> 新建类型
        </button>
        <span className="text-xs text-gray-400">{types.length} 个类型</span>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="bg-white border rounded-xl p-4 space-y-3">
          <h4 className="text-sm font-semibold">新建对象类型</h4>
          <input value={form.name_cn} onChange={e => setForm({ ...form, name_cn: e.target.value })}
            placeholder="中文名 *" className="w-full border rounded-lg px-3 py-2 text-sm" />
          <input value={form.name_en} onChange={e => setForm({ ...form, name_en: e.target.value })}
            placeholder="英文名" className="w-full border rounded-lg px-3 py-2 text-sm" />
          <input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
            placeholder="描述" className="w-full border rounded-lg px-3 py-2 text-sm" />

          {/* 可视化字段定义 */}
          <div className="border-t pt-3">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-medium text-gray-500">属性字段定义 (property_schema)</p>
              <button onClick={addField}
                className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800">
                <Plus size={12} /> 添加字段
              </button>
            </div>
            {schemaFields.length === 0 && (
              <p className="text-xs text-gray-400 py-2">暂无字段，点击"添加字段"开始定义属性</p>
            )}
            <div className="space-y-2">
              {schemaFields.map(f => (
                <div key={f.key} className="flex items-center gap-2">
                  <GripVertical size={12} className="text-gray-300 flex-shrink-0" />
                  <input value={f.name} onChange={e => updateField(f.key, { name: e.target.value })}
                    placeholder="字段名" className="flex-1 border rounded px-2 py-1.5 text-xs" />
                  <select value={f.type} onChange={e => updateField(f.key, { type: e.target.value })}
                    className="border rounded px-2 py-1.5 text-xs w-20">
                    <option value="string">文本</option>
                    <option value="number">数字</option>
                    <option value="boolean">布尔</option>
                  </select>
                  <input value={f.unit} onChange={e => updateField(f.key, { unit: e.target.value })}
                    placeholder="单位" className="border rounded px-2 py-1.5 text-xs w-16" />
                  <button onClick={() => removeField(f.key)}
                    className="text-gray-300 hover:text-red-500"><Trash2 size={12} /></button>
                </div>
              ))}
            </div>
          </div>

          <div className="flex gap-2">
            <button onClick={() => createMut.mutate({
              name_cn: form.name_cn, name_en: form.name_en,
              description: form.description,
              property_schema: buildPropertySchema(),
            })} disabled={!form.name_cn}
              className="flex items-center gap-1 px-3 py-1.5 bg-black text-white rounded-lg text-sm disabled:opacity-40">
              <Save size={12} /> 保存
            </button>
            <button onClick={() => setShowCreate(false)}
              className="px-3 py-1.5 border rounded-lg text-sm text-gray-500"><X size={12} /> 取消</button>
          </div>
        </div>
      )}

      <div className="grid gap-4">
        {filtered.map((ot: ObjectType) => {
          const otFieldEntries = Object.entries(ot.property_schema || {})
          const ifaces = (ot.interface_ids || []).map((id: string) => ifaceMap[id] || id.slice(0, 8))
          const isEditing = editId === ot.id

          if (isEditing) {
            return (
              <div key={ot.id} className="bg-white border rounded-xl p-5 space-y-3 bg-blue-50/30">
                <h4 className="text-sm font-semibold">编辑：{ot.name_cn}</h4>
                <input value={form.name_cn} onChange={e => setForm({ ...form, name_cn: e.target.value })}
                  placeholder="中文名" className="w-full border rounded-lg px-3 py-2 text-sm" />
                <input value={form.name_en} onChange={e => setForm({ ...form, name_en: e.target.value })}
                  placeholder="英文名" className="w-full border rounded-lg px-3 py-2 text-sm" />
                <input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
                  placeholder="描述" className="w-full border rounded-lg px-3 py-2 text-sm" />
                {/* 可视化字段编辑 */}
                <div className="border-t pt-3">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-medium text-gray-500">属性字段</p>
                    <button onClick={addField}
                      className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800">
                      <Plus size={12} /> 添加字段
                    </button>
                  </div>
                  <div className="space-y-2">
                    {schemaFields.map(f => (
                      <div key={f.key} className="flex items-center gap-2">
                        <input value={f.name} onChange={e => updateField(f.key, { name: e.target.value })}
                          placeholder="字段名" className="flex-1 border rounded px-2 py-1.5 text-xs" />
                        <select value={f.type} onChange={e => updateField(f.key, { type: e.target.value })}
                          className="border rounded px-2 py-1.5 text-xs w-20">
                          <option value="string">文本</option>
                          <option value="number">数字</option>
                          <option value="boolean">布尔</option>
                        </select>
                        <input value={f.unit} onChange={e => updateField(f.key, { unit: e.target.value })}
                          placeholder="单位" className="border rounded px-2 py-1.5 text-xs w-16" />
                        <button onClick={() => removeField(f.key)}
                          className="text-gray-300 hover:text-red-500"><Trash2 size={12} /></button>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => updateMut.mutate({ id: ot.id, data: {
                    name_cn: form.name_cn, name_en: form.name_en,
                    description: form.description,
                    property_schema: buildPropertySchema(),
                  }})}
                    className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm">
                    <Save size={12} /> 更新
                  </button>
                  <button onClick={() => setEditId(null)}
                    className="px-3 py-1.5 border rounded-lg text-sm text-gray-500"><X size={12} /> 取消</button>
                </div>
              </div>
            )
          }

          return (
            <div key={ot.id} className="bg-white border rounded-xl p-5 hover:shadow-sm transition-shadow">
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-gray-800">{ot.name_cn}</h3>
                    <button onClick={() => startEdit(ot)}
                      className="text-gray-300 hover:text-gray-600"><Pencil size={12} /></button>
                    <button onClick={() => { if (confirm(`删除类型 "${ot.name_cn}"？`)) deleteMut.mutate(ot.id) }}
                      className="text-gray-300 hover:text-red-500"><Trash2 size={12} /></button>
                  </div>
                  {ot.name_en && <p className="text-xs text-gray-400 font-mono">{ot.name_en}</p>}
                </div>
                <Layers size={18} className="text-gray-300" />
              </div>
              {ot.description && <p className="text-sm text-gray-500 mb-3">{ot.description}</p>}

              {otFieldEntries.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs text-gray-400 mb-2 font-medium uppercase">属性 Schema（可量化字段）</p>
                  <div className="flex flex-wrap gap-1.5">
                    {otFieldEntries.map(([field, def]) => (
                      <span key={field}
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono ${
                          def.type === 'number' ? 'bg-blue-50 text-blue-700' :
                          def.type === 'string' ? 'bg-green-50 text-green-700' :
                          def.type === 'boolean' ? 'bg-purple-50 text-purple-700' :
                          'bg-gray-50 text-gray-600'
                        }`}>
                        {field}
                        <span className="opacity-50">:{def.type}{def.unit ? `(${def.unit})` : ''}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {ifaces.length > 0 && (
                <div>
                  <p className="text-xs text-gray-400 mb-1.5 font-medium uppercase">实现的接口</p>
                  <div className="flex flex-wrap gap-1.5">
                    {ifaces.map((name: string) => (
                      <span key={name} className="px-2 py-0.5 rounded text-[10px] bg-amber-50 text-amber-700 border border-amber-200">
                        {name}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
