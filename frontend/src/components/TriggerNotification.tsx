import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { skillApi } from '@/api/skills'
import type { SkillTrigger } from '@/types/skill'
import { Bell, X, Check, Ban, Loader2, ExternalLink } from 'lucide-react'

/**
 * 轮询 pending triggers，弹出确认窗口。
 * 放在 Layout 中即可全局生效。
 */
export default function TriggerNotification() {
  const navigate = useNavigate()
  const [pending, setPending] = useState<SkillTrigger[]>([])
  const [active, setActive] = useState<SkillTrigger | null>(null) // 当前弹窗显示的
  const [seen, setSeen] = useState<Set<string>>(new Set()) // 已弹过的 ID
  const [actionLoading, setActionLoading] = useState(false)
  const [result, setResult] = useState<{ ontology_id?: string; message: string; status: string } | null>(null)

  const poll = useCallback(async () => {
    try {
      const data = (await skillApi.listPendingTriggers()) as SkillTrigger[]
      setPending(data)
    } catch {
      // ignore polling errors
    }
  }, [])

  // Poll every 10 seconds
  useEffect(() => {
    poll()
    const id = setInterval(poll, 10_000)
    return () => clearInterval(id)
  }, [poll])

  // When new pending triggers appear, show the first unseen one
  useEffect(() => {
    const unseen = pending.filter(t => !seen.has(t.id))
    if (unseen.length > 0 && !active) {
      setActive(unseen[0])
      setSeen(prev => new Set([...prev, unseen[0].id]))
    }
  }, [pending, seen, active])

  const handleConfirm = async () => {
    if (!active) return
    setActionLoading(true)
    try {
      const res = await skillApi.confirmTrigger(active.id) as {
        trigger_id: string; ontology_id: string; extraction_task_id: string; status: string; message: string
      }
      setResult({ ontology_id: res.ontology_id, message: '本体项目已创建，抽取任务已启动', status: 'confirmed' })
    } catch (err: any) {
      setResult({ message: err?.message || err?.detail || '确认失败', status: 'error' })
    } finally {
      setActionLoading(false)
    }
  }

  const handleReject = async () => {
    if (!active) return
    setActionLoading(true)
    try {
      await skillApi.rejectTrigger(active.id)
      setResult({ message: '已拒绝', status: 'rejected' })
    } catch {
      setResult({ message: '操作失败', status: 'error' })
    } finally {
      setActionLoading(false)
    }
  }

  const close = () => {
    setActive(null)
    setResult(null)
  }

  if (!active) return null

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[100]" onClick={close}>
      <div className="bg-white rounded-xl shadow-2xl p-6 w-[460px] max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        {result ? (
          // ── Result view ──
          <div className="text-center">
            <div className={`text-3xl mb-3 ${result.status === 'confirmed' ? 'text-green-500' : result.status === 'rejected' ? 'text-gray-400' : 'text-red-500'}`}>
              {result.status === 'confirmed' ? '✅' : result.status === 'rejected' ? '🚫' : '❌'}
            </div>
            <h3 className="font-semibold mb-2">{result.message}</h3>
            {result.ontology_id && (
              <button
                onClick={() => { close(); navigate(`/ontologies/${result.ontology_id}`) }}
                className="inline-flex items-center gap-1.5 mt-2 px-4 py-2 bg-black text-white rounded-lg text-sm"
              >
                <ExternalLink size={14} /> 查看本体项目
              </button>
            )}
            <button onClick={close} className="block w-full mt-3 px-4 py-2 border rounded-lg text-sm">
              关闭
            </button>
          </div>
        ) : (
          // ── Confirm view ──
          <>
            <div className="flex justify-between items-center mb-4">
              <div className="flex items-center gap-2">
                <Bell size={18} className="text-amber-500" />
                <h3 className="font-semibold text-lg">技能触发通知</h3>
              </div>
              <button onClick={close} className="text-gray-400 hover:text-black"><X size={16} /></button>
            </div>

            <div className="bg-gray-50 rounded-lg p-4 mb-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">技能名称</span>
                <span className="font-medium">{active.skill_name || '未知'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">输入文件</span>
                <span className="font-medium">{active.input_file_name}</span>
              </div>
              {active.input_metadata && Object.keys(active.input_metadata).length > 0 && (
                <div className="flex justify-between">
                  <span className="text-gray-500">附加数据</span>
                  <span className="font-mono text-xs max-w-[200px] truncate">
                    {JSON.stringify(active.input_metadata)}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-gray-500">触发时间</span>
                <span>{new Date(active.created_at).toLocaleString('zh-CN')}</span>
              </div>
            </div>

            <p className="text-sm text-gray-500 mb-4">
              外部系统触发此技能，确认后将自动创建本体项目并启动抽取任务。
            </p>

            <div className="flex gap-3">
              <button
                onClick={handleReject}
                disabled={actionLoading}
                className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 border rounded-lg text-sm text-red-600 hover:bg-red-50 disabled:opacity-50"
              >
                {actionLoading ? <Loader2 size={14} className="animate-spin" /> : <Ban size={14} />}
                拒绝
              </button>
              <button
                onClick={handleConfirm}
                disabled={actionLoading}
                className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 bg-black text-white rounded-lg text-sm disabled:opacity-50"
              >
                {actionLoading ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                确认执行
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
