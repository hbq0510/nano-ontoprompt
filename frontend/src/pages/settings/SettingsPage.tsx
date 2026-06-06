import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { settingsApi, usersApi, promptApi } from '@/api/ontologies'
import { Trash2, Plus, Pencil, X, Check, ChevronDown, ChevronRight, Sparkles } from 'lucide-react'
import {
  EXTRACTION_RULES,
  VALIDATION_RULES,
  loadRuleStates,
  saveRuleStates,
  loadValidationStates,
  saveValidationStates,
  type ExtractionRuleState,
} from '@/utils/extractionRules'

type ActiveTab = 'rules' | 'extraction_rules' | 'users' | 'prompts'

export default function SettingsPage() {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState<ActiveTab>('rules')
  const [ruleValues, setRuleValues] = useState<Record<string, string>>({})
  const [extractStates, setExtractStates] = useState<Record<string, ExtractionRuleState>>(loadRuleStates)
  const [validationStates, setValidationStates] = useState<Record<string, boolean>>(loadValidationStates)
  const [showCreateUser, setShowCreateUser] = useState(false)
  const [userMsg, setUserMsg] = useState('')
  const [editingUserId, setEditingUserId] = useState<string | null>(null)

  // Prompts tab state
  const [showCreatePrompt, setShowCreatePrompt] = useState(false)
  const [promptMsg, setPromptMsg] = useState('')
  const [expandedPromptId, setExpandedPromptId] = useState<string | null>(null)
  const [promptName, setPromptName] = useState('')
  const [promptDomain, setPromptDomain] = useState('通用')
  const [promptContent, setPromptContent] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)

  const { register: regUser, handleSubmit: handleUserSubmit, reset: resetUser } =
    useForm<{ username: string; email: string; password: string; role: string }>()
  const { register: regEdit, handleSubmit: handleEditSubmit, reset: resetEdit } =
    useForm<{ username: string; email: string; password: string; role: string }>()

  const { data: rules = [], isLoading } = useQuery({
    queryKey: ['settings-rules'],
    queryFn: async () => {
      const data = await settingsApi.getRules() as any[]
      const vals: Record<string, string> = {}
      data.forEach((r: any) => { vals[r.rule_key] = r.rule_value })
      setRuleValues(vals)
      return data
    },
  })

  const { data: users = [], isLoading: usersLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list() as any,
    enabled: activeTab === 'users',
  })

  const updateMut = useMutation({
    mutationFn: () => settingsApi.updateRules(
      Object.entries(ruleValues).map(([rule_key, rule_value]) => ({ rule_key, rule_value }))
    ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings-rules'] }),
  })

  const createUserMut = useMutation({
    mutationFn: (data: { username: string; email: string; password: string; role: string }) =>
      usersApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] })
      setShowCreateUser(false)
      resetUser()
      setUserMsg(t('settings.user_created'))
      setTimeout(() => setUserMsg(''), 3000)
    },
    onError: (e: any) => setUserMsg(t('settings.create_failed', { error: e?.detail || '' })),
  })

  const updateUserMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => usersApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] })
      setEditingUserId(null)
      setUserMsg(t('settings.user_updated'))
      setTimeout(() => setUserMsg(''), 3000)
    },
    onError: (e: any) => setUserMsg(t('settings.update_failed', { error: e?.detail || '' })),
  })

  const deleteUserMut = useMutation({
    mutationFn: (id: string) => usersApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })

  const { data: prompts = [], isLoading: promptsLoading } = useQuery({
    queryKey: ['prompts'],
    queryFn: () => promptApi.list() as any,
    enabled: activeTab === 'prompts',
  })

  const createPromptMut = useMutation({
    mutationFn: (data: { name: string; domain: string; content: string; version: string }) =>
      promptApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prompts'] })
      setShowCreatePrompt(false)
      setPromptName('')
      setPromptDomain('通用')
      setPromptContent('')
      setPromptMsg('提示词创建成功')
      setTimeout(() => setPromptMsg(''), 3000)
    },
    onError: (e: any) => setPromptMsg(`创建失败：${e?.detail || e?.message || ''}`),
  })

  async function handleGenerateTemplate() {
    if (!promptDomain) return
    setIsGenerating(true)
    try {
      const result = await promptApi.generateTemplate(promptDomain) as any
      setPromptContent(result.content ?? result)
    } catch (e: any) {
      setPromptMsg(`生成失败：${e?.detail || e?.message || ''}`)
      setTimeout(() => setPromptMsg(''), 3000)
    } finally {
      setIsGenerating(false)
    }
  }

  function startEditUser(u: any) {
    setEditingUserId(u.id)
    resetEdit({ username: u.username, email: u.email ?? '', password: '', role: u.role })
  }

  function updateExtractRule(id: string, patch: Partial<ExtractionRuleState>) {
    setExtractStates(prev => {
      const next = { ...prev, [id]: { ...prev[id], ...patch } }
      saveRuleStates(next)
      return next
    })
  }

  function toggleValidationRule(id: string) {
    setValidationStates(prev => {
      const next = { ...prev, [id]: !prev[id] }
      saveValidationStates(next)
      return next
    })
  }

  const tabs: { key: ActiveTab; label: string }[] = [
    { key: 'rules', label: t('settings.rules') },
    { key: 'extraction_rules', label: t('settings.tab_extraction') },
    { key: 'users', label: t('settings.tab_users') },
    { key: 'prompts', label: '提示词模版' },
  ]

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">{t('settings.title')}</h2>

      <div className="border-b mb-6">
        <div className="flex gap-1">
          {tabs.map(tab => (
            <button key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 ${activeTab === tab.key ? 'border-black' : 'border-transparent text-gray-500'}`}>
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === 'rules' && (
        <div className="max-w-lg">
          <div className="bg-white border rounded-lg p-6 space-y-4">
            {isLoading ? <p className="text-gray-400">{t('common.loading')}</p> : (rules as any[]).map((r: any) => (
              <div key={r.rule_key} className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">{r.rule_label_cn}</p>
                  <p className="text-xs text-gray-400">{r.rule_label_en}</p>
                </div>
                {r.editable ? (
                  <input
                    value={ruleValues[r.rule_key] ?? r.rule_value}
                    onChange={e => setRuleValues(prev => ({ ...prev, [r.rule_key]: e.target.value }))}
                    className="w-24 border rounded-lg px-2 py-1 text-sm text-right"
                  />
                ) : (
                  <span className="text-sm text-gray-500">{r.rule_value}</span>
                )}
              </div>
            ))}
            <div className="pt-2 flex justify-end">
              <button onClick={() => updateMut.mutate()} disabled={updateMut.isPending}
                className="px-4 py-2 bg-black text-white rounded-lg text-sm disabled:opacity-50">
                {t('settings.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'extraction_rules' && (
        <div className="max-w-2xl space-y-6">
          <div>
            <h3 className="text-sm font-semibold mb-1">{t('settings.llm_constraints')}</h3>
            <p className="text-xs text-gray-500 mb-3">{t('settings.llm_constraints_desc')}</p>
            <div className="bg-white border rounded-lg divide-y">
              {EXTRACTION_RULES.map(rule => {
                const state = extractStates[rule.id] ?? { enabled: rule.default_enabled, value: rule.default_value }
                return (
                  <div key={rule.id} className="p-4 flex items-start gap-4">
                    <div className="flex-1">
                      <p className="text-sm font-medium">{rule.label_cn}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{rule.description_cn}</p>
                      {rule.has_value && state.enabled && (
                        <div className="flex items-center gap-2 mt-2">
                          <span className="text-xs text-gray-500">
                            {rule.id === 'min_confidence' ? t('settings.min_confidence') : t('settings.min_docs')}
                          </span>
                          <input
                            type="number"
                            min={rule.id === 'min_confidence' ? 0.1 : 2}
                            max={rule.id === 'min_confidence' ? 1 : 10}
                            step={rule.id === 'min_confidence' ? 0.05 : 1}
                            value={state.value ?? rule.default_value}
                            onChange={e => updateExtractRule(rule.id, { value: Number(e.target.value) })}
                            className="w-20 border rounded px-2 py-0.5 text-sm"
                          />
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => updateExtractRule(rule.id, { enabled: !state.enabled })}
                      className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors ${state.enabled ? 'bg-black' : 'bg-gray-200'}`}>
                      <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${state.enabled ? 'translate-x-[18px]' : 'translate-x-0.5'}`} />
                    </button>
                  </div>
                )
              })}
            </div>
            <p className="text-xs text-gray-400 mt-2">{t('settings.docs_hint')}</p>
          </div>

          <div>
            <h3 className="text-sm font-semibold mb-1">{t('settings.quality_rules')}</h3>
            <p className="text-xs text-gray-500 mb-3">{t('settings.quality_rules_desc')}</p>
            <div className="bg-white border rounded-lg divide-y">
              {VALIDATION_RULES.map(rule => {
                const enabled = validationStates[rule.id] ?? true
                return (
                  <div key={rule.id} className="p-4 flex items-start gap-4">
                    <div className="flex-1">
                      <p className="text-sm font-medium">{rule.label_cn}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{rule.description_cn}</p>
                    </div>
                    <button
                      onClick={() => toggleValidationRule(rule.id)}
                      className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors ${enabled ? 'bg-black' : 'bg-gray-200'}`}>
                      <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${enabled ? 'translate-x-[18px]' : 'translate-x-0.5'}`} />
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'prompts' && (
        <div className="max-w-2xl">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-gray-500">管理提示词模版，用于知识图谱抽取</p>
            <button
              onClick={() => { setShowCreatePrompt(v => !v); setPromptMsg('') }}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-black text-white rounded-lg text-sm">
              <Plus size={14} /> 新建提示词
            </button>
          </div>

          {promptMsg && (
            <p className={`text-xs mb-3 ${promptMsg.includes('成功') ? 'text-green-600' : 'text-red-500'}`}>{promptMsg}</p>
          )}

          {showCreatePrompt && (
            <div className="bg-gray-50 border rounded-lg p-4 mb-4">
              <h4 className="font-medium text-sm mb-3">创建提示词模版</h4>
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">名称 *</label>
                    <input
                      value={promptName}
                      onChange={e => setPromptName(e.target.value)}
                      placeholder="提示词名称"
                      className="w-full border rounded-lg px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">领域 *</label>
                    <select
                      value={promptDomain}
                      onChange={e => setPromptDomain(e.target.value)}
                      className="w-full border rounded-lg px-3 py-2 text-sm">
                      {['供应链', '法律', '医疗', 'HR', '财务', '教育', '通用', '其他'].map(d => (
                        <option key={d} value={d}>{d}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="block text-xs text-gray-500">内容 *</label>
                    <button
                      type="button"
                      onClick={handleGenerateTemplate}
                      disabled={isGenerating}
                      className="flex items-center gap-1 px-2.5 py-1 border border-gray-300 rounded text-xs text-gray-700 hover:bg-gray-100 disabled:opacity-50">
                      <Sparkles size={12} />
                      {isGenerating ? '生成中...' : '✨ 一键生成模版'}
                    </button>
                  </div>
                  <textarea
                    value={promptContent}
                    onChange={e => setPromptContent(e.target.value)}
                    placeholder="输入提示词内容，或点击右上角一键生成..."
                    rows={8}
                    className="w-full border rounded-lg px-3 py-2 text-sm font-mono resize-y"
                  />
                </div>
                <div className="flex gap-2 justify-end">
                  <button
                    type="button"
                    onClick={() => { setShowCreatePrompt(false); setPromptName(''); setPromptDomain('通用'); setPromptContent('') }}
                    className="px-3 py-1.5 border rounded-lg text-sm">
                    取消
                  </button>
                  <button
                    type="button"
                    disabled={createPromptMut.isPending || !promptName.trim() || !promptContent.trim()}
                    onClick={() => createPromptMut.mutate({ name: promptName.trim(), domain: promptDomain, content: promptContent.trim(), version: '1.0' })}
                    className="px-3 py-1.5 bg-black text-white rounded-lg text-sm disabled:opacity-50">
                    {createPromptMut.isPending ? '保存中...' : '确认保存'}
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="bg-white border rounded-lg overflow-hidden">
            {promptsLoading ? (
              <p className="text-center text-gray-400 py-6 text-sm">加载中...</p>
            ) : (prompts as any[]).length === 0 ? (
              <p className="text-center text-gray-400 py-6 text-sm">暂无提示词模版</p>
            ) : (
              <div className="divide-y">
                {(prompts as any[]).map((p: any) => (
                  <div key={p.id}>
                    <button
                      onClick={() => setExpandedPromptId(expandedPromptId === p.id ? null : p.id)}
                      className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 text-left">
                      <span className="text-gray-400 flex-shrink-0">
                        {expandedPromptId === p.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </span>
                      <span className="flex-1 text-sm font-medium">{p.name}</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">{p.domain}</span>
                      <span className="text-xs text-gray-400">v{p.version}</span>
                    </button>
                    {expandedPromptId === p.id && (
                      <div className="px-4 pb-4">
                        <pre className="text-xs text-gray-600 bg-gray-50 rounded-lg p-3 whitespace-pre-wrap font-mono max-h-60 overflow-y-auto">
                          {p.content}
                        </pre>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'users' && (
        <div className="max-w-2xl">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-gray-500">{t('settings.users_desc')}</p>
            <button
              onClick={() => { setShowCreateUser(v => !v); setUserMsg('') }}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-black text-white rounded-lg text-sm">
              <Plus size={14} /> {t('settings.new_user')}
            </button>
          </div>

          {userMsg && (
            <p className={`text-xs mb-3 ${userMsg === t('settings.user_created') || userMsg === t('settings.user_updated') ? 'text-green-600' : 'text-red-500'}`}>{userMsg}</p>
          )}

          {showCreateUser && (
            <div className="bg-gray-50 border rounded-lg p-4 mb-4">
              <h4 className="font-medium text-sm mb-3">{t('settings.create_user')}</h4>
              <form onSubmit={handleUserSubmit(d => createUserMut.mutate(d))} className="grid grid-cols-2 gap-3">
                <input {...regUser('username', { required: true })} placeholder={t('settings.username_required')}
                  className="border rounded-lg px-3 py-2 text-sm" />
                <input {...regUser('email')} placeholder={t('settings.email_optional')} type="email"
                  className="border rounded-lg px-3 py-2 text-sm" />
                <input {...regUser('password', { required: true })} placeholder={t('settings.password_required')} type="password"
                  className="border rounded-lg px-3 py-2 text-sm" />
                <select {...regUser('role')} className="border rounded-lg px-3 py-2 text-sm">
                  <option value="user">{t('settings.role_user')}</option>
                  <option value="admin">{t('settings.role_admin')}</option>
                </select>
                <div className="col-span-2 flex gap-2 justify-end">
                  <button type="button" onClick={() => setShowCreateUser(false)}
                    className="px-3 py-1.5 border rounded-lg text-sm">{t('common.cancel')}</button>
                  <button type="submit" disabled={createUserMut.isPending}
                    className="px-3 py-1.5 bg-black text-white rounded-lg text-sm disabled:opacity-50">
                    {createUserMut.isPending ? t('settings.creating') : t('settings.confirm_create')}
                  </button>
                </div>
              </form>
            </div>
          )}

          <div className="bg-white border rounded-lg overflow-hidden">
            {usersLoading ? (
              <p className="text-center text-gray-400 py-6 text-sm">{t('common.loading')}</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    {[t('settings.col_username'), t('settings.col_email'), t('settings.col_role'), t('settings.col_created'), t('settings.col_actions')].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-medium text-gray-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(users as any[]).map((u: any) => editingUserId === u.id ? (
                    <tr key={u.id} className="border-b bg-gray-50">
                      <td colSpan={5} className="px-4 py-3">
                        <form onSubmit={handleEditSubmit(d => {
                          const payload: any = { username: d.username, email: d.email, role: d.role }
                          if (d.password) payload.password = d.password
                          updateUserMut.mutate({ id: u.id, data: payload })
                        })} className="grid grid-cols-4 gap-2 items-end">
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">{t('settings.col_username')}</label>
                            <input {...regEdit('username', { required: true })}
                              className="w-full border rounded px-2 py-1.5 text-sm" />
                          </div>
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">{t('settings.col_email')}</label>
                            <input {...regEdit('email')} type="email"
                              className="w-full border rounded px-2 py-1.5 text-sm" />
                          </div>
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">{t('settings.new_password_label')}</label>
                            <input {...regEdit('password')} type="password" placeholder={t('settings.password_placeholder')}
                              className="w-full border rounded px-2 py-1.5 text-sm" />
                          </div>
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">{t('settings.col_role')}</label>
                            <select {...regEdit('role')} className="w-full border rounded px-2 py-1.5 text-sm">
                              <option value="user">{t('settings.role_user')}</option>
                              <option value="admin">{t('settings.role_admin')}</option>
                            </select>
                          </div>
                          <div className="col-span-4 flex justify-end gap-2 mt-1">
                            <button type="button" onClick={() => setEditingUserId(null)}
                              className="flex items-center gap-1 px-3 py-1.5 border rounded text-sm text-gray-600">
                              <X size={13} /> {t('common.cancel')}
                            </button>
                            <button type="submit" disabled={updateUserMut.isPending}
                              className="flex items-center gap-1 px-3 py-1.5 bg-black text-white rounded text-sm disabled:opacity-50">
                              <Check size={13} /> {t('common.save')}
                            </button>
                          </div>
                        </form>
                      </td>
                    </tr>
                  ) : (
                    <tr key={u.id} className="border-b last:border-0">
                      <td className="px-4 py-3 font-medium">{u.username}</td>
                      <td className="px-4 py-3 text-gray-500">{u.email || '—'}</td>
                      <td className="px-4 py-3">
                        <span className={`text-xs px-2 py-0.5 rounded-full ${u.role === 'admin' ? 'bg-black text-white' : 'bg-gray-100 text-gray-600'}`}>
                          {u.role === 'admin' ? t('settings.role_admin') : t('settings.role_user')}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-500">
                        {u.created_at ? new Date(u.created_at).toLocaleDateString(i18n.language === 'zh' ? 'zh-CN' : 'en-US') : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <button onClick={() => startEditUser(u)}
                            className="text-gray-500 hover:text-black">
                            <Pencil size={14} />
                          </button>
                          <button onClick={() => {
                            if (confirm(t('settings.confirm_delete_user', { name: u.username }))) deleteUserMut.mutate(u.id)
                          }} className="text-red-500 hover:text-red-700">
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

    </div>
  )
}
