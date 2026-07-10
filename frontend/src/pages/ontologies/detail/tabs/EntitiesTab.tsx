import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ontologyApi } from '@/api/ontologies'
import ConfidenceBar from '@/components/ConfidenceBar'
import ConfirmDialog from '@/components/ConfirmDialog'
import { Pencil, Trash2, Plus, Search, Layers, ChevronDown, ChevronUp } from 'lucide-react'
import type { Entity, EntityTemplate } from '@/types/ontology'

export default function EntitiesTab({ ontologyId }: { ontologyId: string }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [searchQ, setSearchQ] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [groupByType, setGroupByType] = useState(false)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  const [deleteTarget, setDeleteTarget] = useState<Entity | null>(null)
  const [createType, setCreateType] = useState('')
  const [createProps, setCreateProps] = useState<Record<string, string>>({})

  const { data: entities = [], isLoading } = useQuery({
    queryKey: ['entities', ontologyId],
    queryFn: () => ontologyApi.listEntities(ontologyId) as any,
  })

  const { data: templates = [] } = useQuery({
    queryKey: ['templates', ontologyId],
    queryFn: () => ontologyApi.listTemplates(ontologyId) as Promise<EntityTemplate[]>,
  })

  const activeTemplate = templates.find(t => t.type_name === createType)

  const createMut = useMutation({
    mutationFn: (data: Partial<Entity>) => ontologyApi.createEntity(ontologyId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['entities', ontologyId] }); qc.invalidateQueries({ queryKey: ['stats'] }); setShowCreate(false); setCreateType(''); setCreateProps({}) },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => ontologyApi.deleteEntity(ontologyId, id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['entities', ontologyId] }); qc.invalidateQueries({ queryKey: ['stats'] }) },
  })

  const allTypes = useMemo(() => {
    const s = new Set<string>()
    ;(entities as Entity[]).forEach(e => { if (e.type) s.add(e.type) })
    return Array.from(s).sort()
  }, [entities])

  const filtered = useMemo(() => {
    const q = searchQ.trim().toLowerCase()
    return (entities as Entity[]).filter(e => {
      const matchQ = !q || e.name_cn?.toLowerCase().includes(q) || e.name_en?.toLowerCase().includes(q) || e.type?.toLowerCase().includes(q)
      const matchType = !typeFilter || e.type === typeFilter
      return matchQ && matchType
    })
  }, [entities, searchQ, typeFilter])

  // 按类型分组
  const groupedEntities = useMemo(() => {
    const g: Record<string, Entity[]> = {}
    filtered.forEach(e => {
      const key = e.type || '未分类'
      if (!g[key]) g[key] = []
      g[key].push(e)
    })
    return g
  }, [filtered])

  const toggleGroup = (typeName: string) => {
    const next = new Set(expandedGroups)
    next.has(typeName) ? next.delete(typeName) : next.add(typeName)
    setExpandedGroups(next)
  }

  return (
    <div className="space-y-4">
      {/* Search bar */}
      <div className="flex gap-2 items-center">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <input value={searchQ} onChange={e => setSearchQ(e.target.value)}
            placeholder="搜索名称 / 类型…"
            className="w-full border rounded-lg pl-8 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black" />
        </div>
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
          className="border rounded-lg px-3 py-2 text-sm text-gray-600">
          <option value="">全部类型</option>
          {allTypes.map(tp => <option key={tp} value={tp}>{tp}</option>)}
        </select>
      </div>
      <div className="flex justify-end gap-2">
        <button onClick={() => { setGroupByType(!groupByType); setExpandedGroups(new Set()) }}
          className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border transition-colors ${
            groupByType ? 'bg-blue-50 border-blue-300 text-blue-700' : 'border-gray-200 text-gray-500 hover:bg-gray-50'
          }`}>
          <Layers size={14} /> 按类型分组
        </button>
        <button onClick={() => { setShowCreate(true); setCreateType(''); setCreateProps({}) }}
          className="flex items-center gap-2 px-3 py-2 bg-black text-white rounded-lg text-sm">
          <Plus size={14} /> {t('entities.add')}
        </button>
      </div>

      {/* Table / Grouped view */}
      <div className="bg-white border rounded-lg overflow-hidden">
        {isLoading ? <p className="py-8 text-center text-gray-400">{t('common.loading')}</p> :
        groupByType ? (
          // ── 按类型分组视图 ──
          <div className="divide-y">
            {Object.entries(groupedEntities).sort(([a], [b]) => a.localeCompare(b)).map(([typeName, ents]) => {
              const isExpanded = expandedGroups.has(typeName)
              return (
                <div key={typeName}>
                  <button
                    onClick={() => toggleGroup(typeName)}
                    className="w-full flex items-center gap-2 px-4 py-3 bg-gray-50 hover:bg-gray-100 text-left text-sm font-medium"
                  >
                    {isExpanded ? <ChevronDown size={14} className="text-gray-400" /> : <ChevronUp size={14} className="text-gray-400" />}
                    <span className="px-2 py-0.5 rounded text-xs bg-blue-50 text-blue-700 border border-blue-200">{typeName}</span>
                    <span className="text-gray-400 text-xs">({ents.length} 个实体)</span>
                  </button>
                  {isExpanded && (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b">
                          {[t('entities.col_name_cn'), t('entities.col_name_en'), t('entities.col_desc'), t('entities.col_confidence'), t('entities.col_actions')].map(h => (
                            <th key={h} className="px-4 py-2 text-left text-gray-400 text-xs font-medium">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {ents.map(e => (
                          <tr key={e.id} className="border-b hover:bg-gray-50 cursor-pointer"
                            onClick={() => navigate(`/ontologies/${ontologyId}/entities/${e.id}`)}>
                            <td className="px-4 py-2.5 font-medium">{e.name_cn}</td>
                            <td className="px-4 py-2.5 text-gray-500 text-xs">{e.name_en || '—'}</td>
                            <td className="px-4 py-2.5 text-gray-500 max-w-xs truncate text-xs">{e.description || '—'}</td>
                            <td className="px-4 py-2.5 w-28"><ConfidenceBar value={e.confidence} /></td>
                            <td className="px-4 py-2.5" onClick={ev => ev.stopPropagation()}>
                              <div className="flex items-center gap-2">
                                <button onClick={() => navigate(`/ontologies/${ontologyId}/entities/${e.id}`)} title={t('common.edit')} className="p-1 rounded text-blue-500 hover:bg-blue-50"><Pencil size={13} /></button>
                                <button onClick={() => setDeleteTarget(e)} title={t('common.delete')} className="p-1 rounded text-red-500 hover:bg-red-50"><Trash2 size={13} /></button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )
            })}
          </div>
        ) : (
          // ── 平铺表格视图 ──
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>{[t('entities.col_name_cn'), t('entities.col_name_en'), t('entities.col_type'), t('entities.col_desc'), t('entities.col_confidence'), t('entities.col_actions')].map(h => (
                <th key={h} className="px-4 py-3 text-left text-gray-500 text-xs font-medium">{h}</th>
              ))}</tr>
            </thead>
            <tbody>
              {filtered.map(e => (
                <tr key={e.id} className="border-b hover:bg-gray-50 cursor-pointer"
                  onClick={() => navigate(`/ontologies/${ontologyId}/entities/${e.id}`)}>
                  <td className="px-4 py-3 font-medium">{e.name_cn}</td>
                  <td className="px-4 py-3 text-gray-500">{e.name_en || '—'}</td>
                  <td className="px-4 py-3 text-gray-500">{e.type || '—'}</td>
                  <td className="px-4 py-3 text-gray-500 max-w-xs truncate">{e.description || '—'}</td>
                  <td className="px-4 py-3 w-32"><ConfidenceBar value={e.confidence} /></td>
                  <td className="px-4 py-3" onClick={ev => ev.stopPropagation()}>
                    <div className="flex items-center gap-3">
                      <button onClick={() => navigate(`/ontologies/${ontologyId}/entities/${e.id}`)} title={t('common.edit')} className="p-1.5 rounded text-blue-500 hover:bg-blue-50"><Pencil size={14} /></button>
                      <button onClick={() => setDeleteTarget(e)} title={t('common.delete')} className="p-1.5 rounded text-red-500 hover:bg-red-50"><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!isLoading && filtered.length === 0 && (
          <p className="text-center text-gray-400 py-8">{searchQ || typeFilter ? '无匹配结果' : t('entities.empty')}</p>
        )}
      </div>

      {showCreate && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-[480px] max-h-[80vh] overflow-y-auto">
            <h3 className="font-semibold text-lg mb-1">添加实体</h3>
            <p className="text-xs text-gray-400 mb-4">选择类型后按模板填写字段</p>

            {/* 类型选择 */}
            <div className="mb-3">
              <label className="block text-xs font-medium text-gray-600 mb-1">实体类型</label>
              {templates.length > 0 ? (
                <div className="flex gap-1 flex-wrap">
                  {templates.map(t => (
                    <button key={t.id}
                      onClick={() => { setCreateType(t.type_name); setCreateProps({}) }}
                      className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                        createType === t.type_name
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      }`}>
                      {t.type_name}
                    </button>
                  ))}
                  <button
                    onClick={() => { setCreateType('__custom'); setCreateProps({}) }}
                    className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                      createType === '__custom'
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-200 italic'
                    }`}>
                    自定义...
                  </button>
                </div>
              ) : (
                <input value={createType} onChange={e => setCreateType(e.target.value)}
                  placeholder="如：导弹、坦克" className="w-full border rounded-lg px-3 py-2 text-sm" />
              )}
            </div>

            {/* 按模板渲染字段 */}
            {activeTemplate && (
              <div className="space-y-3 mb-3">
                <div className="text-xs font-medium text-gray-500 bg-gray-50 rounded-lg p-2">
                  📋 {activeTemplate.type_name}模板 · {activeTemplate.fields.filter(f => f.required).length} 个必填字段
                </div>
                {activeTemplate.fields.map(f => (
                  <div key={f.name}>
                    <label className="block text-xs font-medium text-gray-600 mb-0.5">
                      {f.name}{f.required && <span className="text-red-500 ml-0.5">*</span>}
                      {f.unit && <span className="text-gray-400 font-normal ml-1">({f.unit})</span>}
                    </label>
                    {f.type === 'select' ? (
                      <select
                        value={createProps[f.name] || ''}
                        onChange={e => setCreateProps(prev => ({ ...prev, [f.name]: e.target.value }))}
                        required={f.required}
                        className="w-full border rounded-lg px-3 py-2 text-sm">
                        <option value="">-- 请选择 --</option>
                        {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : f.type === 'number' ? (
                      <input
                        value={createProps[f.name] || ''}
                        onChange={e => setCreateProps(prev => ({ ...prev, [f.name]: e.target.value }))}
                        type="number" placeholder={f.name} required={f.required}
                        className="w-full border rounded-lg px-3 py-2 text-sm" />
                    ) : f.type === 'boolean' ? (
                      <label className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                          type="checkbox"
                          checked={createProps[f.name] === 'true'}
                          onChange={e => setCreateProps(prev => ({ ...prev, [f.name]: e.target.checked ? 'true' : '' }))}
                          className="rounded" />
                        {f.name}
                      </label>
                    ) : (
                      <input
                        value={createProps[f.name] || ''}
                        onChange={e => setCreateProps(prev => ({ ...prev, [f.name]: e.target.value }))}
                        placeholder={f.name} required={f.required}
                        className="w-full border rounded-lg px-3 py-2 text-sm" />
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* 通用字段 */}
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-0.5">中文名 *</label>
                <input value={createProps['__name_cn'] || ''}
                  onChange={e => setCreateProps(prev => ({ ...prev, __name_cn: e.target.value }))}
                  placeholder="实体中文名称" required
                  className="w-full border rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-0.5">英文名</label>
                <input value={createProps['__name_en'] || ''}
                  onChange={e => setCreateProps(prev => ({ ...prev, __name_en: e.target.value }))}
                  placeholder="English name"
                  className="w-full border rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-0.5">描述</label>
                <textarea value={createProps['__desc'] || ''}
                  onChange={e => setCreateProps(prev => ({ ...prev, __desc: e.target.value }))}
                  placeholder="简要描述" rows={2}
                  className="w-full border rounded-lg px-3 py-2 text-sm resize-none" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-0.5">置信度</label>
                <input value={createProps['__confidence'] || '0.85'}
                  onChange={e => setCreateProps(prev => ({ ...prev, __confidence: e.target.value }))}
                  type="number" step="0.01" min="0" max="1"
                  className="w-full border rounded-lg px-3 py-2 text-sm" />
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t mt-4">
              <button type="button" onClick={() => { setShowCreate(false); setCreateType(''); setCreateProps({}) }}
                className="px-4 py-2 border rounded-lg text-sm text-gray-500 hover:bg-gray-50">取消</button>
              <button
                onClick={() => {
                  const body: any = {
                    name_cn: createProps['__name_cn'] || '新实体',
                    name_en: createProps['__name_en'] || undefined,
                    type: createType === '__custom' ? '' : createType,
                    description: createProps['__desc'] || undefined,
                    confidence: parseFloat(createProps['__confidence'] || '0.85'),
                    properties: {} as Record<string, any>,
                  }
                  // 提取模板字段到 properties
                  if (activeTemplate) {
                    const props: Record<string, any> = {}
                    activeTemplate.fields.forEach(f => {
                      const val = createProps[f.name]
                      if (val !== undefined && val !== '') {
                        props[f.name] = f.type === 'number' ? parseFloat(val) || val : val
                      }
                    })
                    body.properties = props
                  }
                  createMut.mutate(body)
                }}
                disabled={!createProps['__name_cn']}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-40">
                创建实体
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title={t('entities.delete_title')}
        message={t('entities.delete_confirm', { name: deleteTarget?.name_cn ?? '' })}
        onConfirm={() => { if (deleteTarget) deleteMut.mutate(deleteTarget.id); setDeleteTarget(null) }}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
