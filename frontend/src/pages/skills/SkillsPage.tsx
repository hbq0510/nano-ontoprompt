import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { skillApi } from '@/api/skills'
import { promptApi } from '@/api/ontologies'
import { modelApi } from '@/api/ontologies'
import ConfirmDialog from '@/components/ConfirmDialog'
import type { Skill, SkillListItem } from '@/types/skill'
import type { Prompt, ModelConfig } from '@/types/ontology'
import { SKILL_DOMAINS, INPUT_TYPES } from '@/types/skill'
import { Plus, Pencil, Trash2, X, Loader2, Zap, Play } from 'lucide-react'

export default function SkillsPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [editTarget, setEditTarget] = useState<Skill | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<SkillListItem | null>(null)
  const [triggerFile, setTriggerFile] = useState<{ skill: SkillListItem; file: File | null } | null>(null)

  const { data: skills = [], isLoading } = useQuery({
    queryKey: ['skills'],
    queryFn: () => skillApi.list() as Promise<SkillListItem[]>,
  })

  const { data: prompts = [] } = useQuery({
    queryKey: ['prompts'],
    queryFn: () => promptApi.list() as Promise<Prompt[]>,
  })

  const { data: models = [] } = useQuery({
    queryKey: ['models'],
    queryFn: () => modelApi.list() as Promise<ModelConfig[]>,
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => skillApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['skills'] }); setDeleteTarget(null) },
  })

  const triggerMut = useMutation({
    mutationFn: ({ skillId, file }: { skillId: string; file: File }) =>
      skillApi.trigger(skillId, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pendingTriggers'] })
      setTriggerFile(null)
    },
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold">技能管理</h2>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 bg-black text-white px-4 py-2 rounded-lg text-sm"
        >
          <Plus size={14} /> 新建技能
        </button>
      </div>

      <div className="grid gap-4">
        {isLoading ? (
          <p className="text-gray-400 text-sm">加载中...</p>
        ) : (
          (skills as SkillListItem[]).map(s => (
            <div key={s.id} className="bg-white border rounded-lg p-4">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold">{s.name}</h3>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${s.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                      {s.enabled ? '启用' : '禁用'}
                    </span>
                  </div>
                  <p className="text-sm text-gray-500 mt-1">
                    领域：{s.domain} · {s.description || '暂无描述'}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">
                    创建于 {new Date(s.created_at).toLocaleString('zh-CN')}
                  </p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => setTriggerFile({ skill: s, file: null })}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 border rounded text-xs hover:bg-gray-50 text-green-600"
                  >
                    <Play size={13} /> 触发
                  </button>
                  <button
                    onClick={async () => {
                      const detail = await skillApi.get(s.id) as Skill
                      setEditTarget(detail)
                    }}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 border rounded text-xs hover:bg-gray-50 text-blue-600"
                  >
                    <Pencil size={13} /> 编辑
                  </button>
                  <button
                    onClick={() => setDeleteTarget(s)}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 border rounded text-xs hover:bg-gray-50 text-red-500"
                  >
                    <Trash2 size={13} /> 删除
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
        {!isLoading && skills.length === 0 && (
          <div className="bg-white border rounded-lg p-8 text-center text-gray-400">
            暂无技能，点击「新建技能」创建第一个
          </div>
        )}
      </div>

      {/* 新建 / 编辑弹窗 */}
      {(showCreate || editTarget) && (
        <SkillFormModal
          title={editTarget ? '编辑技能' : '新建技能'}
          initial={editTarget || undefined}
          prompts={prompts as Prompt[]}
          models={models as ModelConfig[]}
          onClose={() => { setShowCreate(false); setEditTarget(null) }}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['skills'] })
            setShowCreate(false)
            setEditTarget(null)
          }}
        />
      )}

      {/* 触发弹窗 */}
      {triggerFile && (
        <TriggerModal
          skill={triggerFile.skill}
          onClose={() => setTriggerFile(null)}
          onTrigger={(file) => triggerMut.mutate({ skillId: triggerFile.skill.id, file })}
          isPending={triggerMut.isPending}
          result={triggerMut.data}
        />
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title="确认删除"
        message={`确定要删除技能「${deleteTarget?.name}」吗？此操作不可撤销。`}
        onConfirm={() => deleteTarget && deleteMut.mutate(deleteTarget.id)}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}

/** 新建/编辑表单弹窗 */
function SkillFormModal({
  title, initial, prompts, models, onClose, onSaved,
}: {
  title: string
  initial?: Skill
  prompts: Prompt[]
  models: ModelConfig[]
  onClose: () => void
  onSaved: () => void
}) {
  const [selectedInputTypes, setSelectedInputTypes] = useState<string[]>(
    initial?.accepted_input_types || ['image/*', 'text/plain'],
  )
  const [entityStr, setEntityStr] = useState((initial?.prebuilt_entities || []).join('\n'))

  const { register, handleSubmit } = useForm({
    defaultValues: initial
      ? {
          name: initial.name,
          description: initial.description || '',
          domain: initial.domain,
          prompt_id: initial.prompt_id || '',
          model_id: initial.model_id || '',
          ontology_name_pattern: initial.ontology_name_pattern || '{skill_name}-{timestamp}',
          enabled: initial.enabled,
        }
      : {
          domain: '军事',
          ontology_name_pattern: '{skill_name}-{timestamp}',
          enabled: true,
        },
  })

  const createMut = useMutation({
    mutationFn: (data: any) =>
      initial
        ? skillApi.update(initial.id, {
            ...data,
            accepted_input_types: selectedInputTypes,
            prebuilt_entities: entityStr.split('\n').map(s => s.trim()).filter(Boolean),
          })
        : skillApi.create({
            ...data,
            accepted_input_types: selectedInputTypes,
            prebuilt_entities: entityStr.split('\n').map(s => s.trim()).filter(Boolean),
          }),
    onSuccess: onSaved,
  })

  const toggleInputType = (value: string) => {
    setSelectedInputTypes(prev =>
      prev.includes(value) ? prev.filter(t => t !== value) : [...prev, value],
    )
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-lg p-6 w-[560px] max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-semibold">{title}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-black"><X size={16} /></button>
        </div>
        <form onSubmit={handleSubmit(d => createMut.mutate(d))} className="space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">名称 *</label>
            <input {...register('name', { required: true })} className="w-full border rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">描述</label>
            <textarea {...register('description')} rows={2} className="w-full border rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1">领域 *</label>
              <select {...register('domain')} className="w-full border rounded-lg px-3 py-2 text-sm">
                {SKILL_DOMAINS.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">状态</label>
              <select {...register('enabled')} className="w-full border rounded-lg px-3 py-2 text-sm">
                <option value="true">启用</option>
                <option value="false">禁用</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">绑定的提示词</label>
            <select {...register('prompt_id')} className="w-full border rounded-lg px-3 py-2 text-sm">
              <option value="">不绑定</option>
              {prompts.map(p => <option key={p.id} value={p.id}>{p.name} ({p.domain})</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">绑定的模型</label>
            <select {...register('model_id')} className="w-full border rounded-lg px-3 py-2 text-sm">
              <option value="">不绑定</option>
              {models.map(m => <option key={m.id} value={m.id}>{m.name} ({m.provider})</option>)}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Ontology 命名模板</label>
            <input {...register('ontology_name_pattern')} className="w-full border rounded-lg px-3 py-2 text-sm font-mono" />
            <p className="text-xs text-gray-400 mt-0.5">可用变量：{'{skill_name}'}, {'{timestamp}'}</p>
          </div>

          <div>
            <label className="text-sm font-medium mb-2 block">接受的输入类型</label>
            <div className="flex flex-wrap gap-2">
              {INPUT_TYPES.map(t => {
                const sel = selectedInputTypes.includes(t.value)
                return (
                  <button
                    key={t.value}
                    type="button"
                    onClick={() => toggleInputType(t.value)}
                    className={`text-xs px-3 py-1.5 rounded-full border ${sel ? 'bg-black text-white border-black' : 'border-gray-200 text-gray-600 hover:bg-gray-50'}`}
                  >
                    {t.label}
                  </button>
                )
              })}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">预定义实体类型（每行一个）</label>
            <textarea
              value={entityStr}
              onChange={e => setEntityStr(e.target.value)}
              rows={4}
              placeholder={'建筑物\n道路\n植被\n水域\n军事设施\n部队单位'}
              className="w-full border rounded-lg px-3 py-2 text-sm font-mono"
            />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 border rounded-lg text-sm">取消</button>
            <button
              type="submit"
              disabled={createMut.isPending}
              className="flex items-center gap-1.5 px-4 py-2 bg-black text-white rounded-lg text-sm disabled:opacity-50"
            >
              {createMut.isPending && <Loader2 size={13} className="animate-spin" />}
              {initial ? '保存' : '创建'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

/** 触发弹窗 */
function TriggerModal({
  skill, onClose, onTrigger, isPending, result,
}: {
  skill: SkillListItem
  onClose: () => void
  onTrigger: (file: File) => void
  isPending: boolean
  result?: { trigger_id: string; status: string; message: string }
}) {
  const [file, setFile] = useState<File | null>(null)

  if (result) {
    return (
      <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
        <div className="bg-white rounded-lg shadow-lg p-6 w-[400px] text-center" onClick={e => e.stopPropagation()}>
          <Zap size={32} className="mx-auto text-green-500 mb-3" />
          <h3 className="font-semibold mb-2">触发成功</h3>
          <p className="text-sm text-gray-600 mb-4">
            技能「{skill.name}」已触发，等待用户确认后开始执行。
          </p>
          <p className="text-xs text-gray-400 mb-4">Trigger ID: {result.trigger_id}</p>
          <button onClick={onClose} className="px-4 py-2 bg-black text-white rounded-lg text-sm">关闭</button>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-lg p-6 w-[420px]" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-semibold">触发技能：{skill.name}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-black"><X size={16} /></button>
        </div>
        <p className="text-sm text-gray-500 mb-4">
          模拟外部系统推送文件触发此技能。选择文件后将创建一条 pending 触发记录。
        </p>
        <div className="mb-4">
          <label className="block text-sm font-medium mb-2">选择文件</label>
          <input
            type="file"
            onChange={e => setFile(e.target.files?.[0] || null)}
            className="w-full border rounded-lg px-3 py-2 text-sm"
          />
        </div>
        <div className="flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 border rounded-lg text-sm">取消</button>
          <button
            onClick={() => file && onTrigger(file)}
            disabled={!file || isPending}
            className="flex items-center gap-1.5 px-4 py-2 bg-black text-white rounded-lg text-sm disabled:opacity-50"
          >
            {isPending && <Loader2 size={13} className="animate-spin" />}
            发送触发
          </button>
        </div>
      </div>
    </div>
  )
}
