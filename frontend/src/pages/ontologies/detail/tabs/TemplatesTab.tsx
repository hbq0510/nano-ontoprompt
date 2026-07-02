import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ontologyApi } from '@/api/ontologies'
import type { EntityTemplate, FieldDef } from '@/types/ontology'
import { Plus, Trash2, Edit2, X, Check, Layers } from 'lucide-react'

const FIELD_TYPES = [
  { value: 'string', label: '文本' },
  { value: 'number', label: '数字' },
  { value: 'select', label: '下拉选择' },
  { value: 'boolean', label: '是/否' },
  { value: 'text', label: '长文本' },
]

export default function TemplatesTab({ ontologyId }: { ontologyId: string }) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<string | null>(null)
  const [form, setForm] = useState({ type_name: '', type_name_en: '', description: '', fields: [] as FieldDef[] })

  const { data: templates, isLoading } = useQuery({
    queryKey: ['templates', ontologyId],
    queryFn: () => ontologyApi.listTemplates(ontologyId) as Promise<EntityTemplate[]>,
  })

  const createMut = useMutation({
    mutationFn: (body: any) => ontologyApi.createTemplate(ontologyId, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['templates', ontologyId] }); cancelEdit() },
  })
  const updateMut = useMutation({
    mutationFn: ({ tid, body }: { tid: string; body: any }) => ontologyApi.updateTemplate(ontologyId, tid, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['templates', ontologyId] }); cancelEdit() },
  })
  const deleteMut = useMutation({
    mutationFn: (tid: string) => ontologyApi.deleteTemplate(ontologyId, tid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['templates', ontologyId] }),
  })

  function cancelEdit() {
    setEditing(null)
    setForm({ type_name: '', type_name_en: '', description: '', fields: [] })
  }

  function startCreate() {
    setEditing('new')
    setForm({ type_name: '', type_name_en: '', description: '', fields: [] })
  }

  function startEdit(t: EntityTemplate) {
    setEditing(t.id)
    setForm({ type_name: t.type_name, type_name_en: t.type_name_en || '', description: t.description || '', fields: [...t.fields] })
  }

  function updateField(i: number, patch: Partial<FieldDef>) {
    setForm(prev => {
      const fields = [...prev.fields]
      fields[i] = { ...fields[i], ...patch }
      return { ...prev, fields }
    })
  }

  function removeField(i: number) {
    setForm(prev => ({ ...prev, fields: prev.fields.filter((_, j) => j !== i) }))
  }

  function addField() {
    setForm(prev => ({
      ...prev,
      fields: [...prev.fields, { name: '', type: 'string', required: true, options: [], unit: '' }],
    }))
  }

  function save() {
    if (!form.type_name.trim()) return
    const body = {
      type_name: form.type_name,
      type_name_en: form.type_name_en || undefined,
      description: form.description || undefined,
      fields: form.fields,
    }
    if (editing === 'new') createMut.mutate(body)
    else if (editing) updateMut.mutate({ tid: editing, body })
  }

  if (isLoading) return <div className="p-8 text-center text-gray-400 text-sm">加载中...</div>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <Layers size={16} /> 实体类型模板
        </h3>
        {!editing && (
          <button onClick={startCreate}
            className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs hover:bg-blue-700 transition-colors">
            <Plus size={14} /> 新建模板
          </button>
        )}
      </div>

      {/* ── Edit / Create form ──────────────────────────────────── */}
      {editing && (
        <div className="bg-blue-50/50 border border-blue-200 rounded-xl p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">类型名称 *</label>
              <input value={form.type_name} onChange={e => setForm(prev => ({ ...prev, type_name: e.target.value }))}
                placeholder="如：导弹、坦克、雷达站" className="w-full border rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">英文名</label>
              <input value={form.type_name_en} onChange={e => setForm(prev => ({ ...prev, type_name_en: e.target.value }))}
                placeholder="Missile" className="w-full border rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">描述</label>
            <input value={form.description} onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
              placeholder="简要描述该类型的用途" className="w-full border rounded-lg px-3 py-2 text-sm" />
          </div>

          {/* ── Fields — inline editable ────────────────────────── */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-600">字段定义</span>
              <button onClick={addField}
                className="flex items-center gap-1 px-2 py-1 text-xs text-blue-600 hover:bg-blue-50 rounded transition-colors">
                <Plus size={12} /> 添加字段
              </button>
            </div>

            {form.fields.length === 0 ? (
              <div className="text-center py-10 text-gray-400 text-xs border-2 border-dashed border-gray-200 rounded-lg">
                暂无字段，点击上方「添加字段」开始定义
              </div>
            ) : (
              <div className="space-y-2">
                {form.fields.map((f, i) => (
                  <div key={i} className="bg-white border rounded-lg p-3 space-y-2">
                    <div className="flex items-center gap-2">
                      <input value={f.name} onChange={e => updateField(i, { name: e.target.value })}
                        placeholder="字段名" className="flex-1 border rounded px-3 py-2 text-sm font-medium min-w-[100px]" />
                      <select value={f.type} onChange={e => updateField(i, { type: e.target.value as FieldDef['type'] })}
                        className="border rounded px-2 py-2 text-sm w-28 shrink-0">
                        {FIELD_TYPES.map(ft => <option key={ft.value} value={ft.value}>{ft.label}</option>)}
                      </select>
                      <input value={f.unit} onChange={e => updateField(i, { unit: e.target.value })}
                        placeholder="单位" className="border rounded px-2 py-2 text-sm w-20 shrink-0" />
                      <label className="flex items-center gap-1 text-sm text-gray-500 cursor-pointer select-none shrink-0">
                        <input type="checkbox" checked={f.required} onChange={e => updateField(i, { required: e.target.checked })} />
                        必填
                      </label>
                      <button onClick={() => removeField(i)}
                        className="p-1.5 text-gray-400 hover:text-red-500 transition-colors shrink-0" title="删除">
                        <Trash2 size={16} />
                      </button>
                    </div>
                    {f.type === 'select' && (
                      <div className="flex items-center gap-2 pl-1">
                        <span className="text-xs text-gray-400 shrink-0">选项：</span>
                        <div className="flex flex-wrap gap-1 flex-1">
                          {f.options.map((opt, oi) => (
                            <span key={oi} className="inline-flex items-center gap-1 bg-blue-50 text-blue-700 text-xs px-2 py-0.5 rounded-full">
                              {opt}
                              <X size={12} className="cursor-pointer hover:text-red-500"
                                onClick={() => {
                                  const updated = [...form.fields]
                                  updated[i] = { ...updated[i], options: updated[i].options.filter((_, j) => j !== oi) }
                                  setForm(prev => ({ ...prev, fields: updated }))
                                }} />
                            </span>
                          ))}
                        </div>
                        <input
                          placeholder="添加选项，回车确认"
                          className="border rounded px-2 py-1 text-xs w-40 shrink-0"
                          onKeyDown={e => {
                            if (e.key === 'Enter') {
                              e.preventDefault()
                              const t = e.target as HTMLInputElement
                              const val = t.value.trim()
                              if (!val) return
                              const updated = [...form.fields]
                              updated[i] = { ...updated[i], options: [...updated[i].options, val] }
                              setForm(prev => ({ ...prev, fields: updated }))
                              t.value = ''
                            }
                          }}
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex gap-2 pt-1">
            <button onClick={save} disabled={!form.type_name.trim()}
              className="flex items-center gap-1 px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700 disabled:opacity-40 transition-colors">
              <Check size={14} /> 保存
            </button>
            <button onClick={cancelEdit}
              className="px-4 py-2 border rounded-lg text-sm text-gray-500 hover:bg-gray-50 transition-colors">取消</button>
          </div>
        </div>
      )}

      {/* ── Template list ───────────────────────────────────────── */}
      {!editing && templates && templates.length === 0 && (
        <div className="text-center py-12 text-gray-400 text-sm">
          <Layers size={32} className="mx-auto mb-2 opacity-30" />
          暂无类型模板，点击「新建模板」创建第一个
        </div>
      )}

      {!editing && templates && templates.length > 0 && (
        <div className="grid grid-cols-2 gap-3">
          {templates.map(t => (
            <div key={t.id} className="bg-white border rounded-xl p-4 hover:shadow-sm transition-shadow">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <h4 className="font-semibold text-gray-800">{t.type_name}</h4>
                  {t.type_name_en && <span className="text-xs text-gray-400">{t.type_name_en}</span>}
                </div>
                <div className="flex gap-1">
                  <button onClick={() => startEdit(t)} className="p-1 text-gray-400 hover:text-blue-600"><Edit2 size={14} /></button>
                  <button onClick={() => { if (confirm(`删除「${t.type_name}」模板？`)) deleteMut.mutate(t.id) }}
                    className="p-1 text-gray-400 hover:text-red-600"><Trash2 size={14} /></button>
                </div>
              </div>
              {t.description && <p className="text-xs text-gray-500 mb-3">{t.description}</p>}
              <div className="flex flex-wrap gap-1">
                {t.fields.map((f, i) => (
                  <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 rounded text-[11px] text-gray-600">
                    {f.name}
                    {f.required && <span className="text-red-400">*</span>}
                    <span className="text-gray-400">({FIELD_TYPES.find(ft => ft.value === f.type)?.label || f.type})</span>
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
