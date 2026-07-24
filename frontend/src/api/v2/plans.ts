/** 方案系统 API */
import { apiClientV2 } from '@/api/client'

export interface DecisionStep {
  trigger: string
  target?: string
  action: string
  params?: Record<string, unknown>
}

export interface PlanData {
  id: string
  scenario_id: string
  name: string
  description?: string
  decisions: DecisionStep[]
  status: 'proposed' | 'running' | 'evaluated'
  score?: Record<string, number>
  source?: string
  template_id?: string
  created_at?: string
}

export interface PlanRunData {
  id: string
  plan_id: string
  status: string
  tick_count: number
  result?: Record<string, number>
  decision_log?: { tick: number; decision: DecisionStep; status: string }[]
  events?: { tick: number; type: string; desc: string }[]
}

export interface CompareData {
  items: { plan_id: string; plan_name: string; score: Record<string, number>; status: string }[]
  best?: { plan_id: string; plan_name: string; score: Record<string, number> }
}

const plansApi = {
  list: (scenarioId: string) =>
    apiClientV2.get<any>(`/scenarios/${scenarioId}/plans`).then(r => r?.data ?? r ?? []),

  get: (scenarioId: string, planId: string) =>
    apiClientV2.get<any>(`/scenarios/${scenarioId}/plans/${planId}`).then(r => r?.data ?? r),

  getPlan: (scenarioId: string, planId: string) =>
    apiClientV2.get<any>(`/scenarios/${scenarioId}/plans/${planId}`).then(r => r?.data ?? r),

  create: (scenarioId: string, data: Partial<PlanData>) =>
    apiClientV2.post<any>(`/scenarios/${scenarioId}/plans`, data).then(r => r?.data ?? r),

  update: (scenarioId: string, planId: string, data: Partial<PlanData>) =>
    apiClientV2.put<any>(`/scenarios/${scenarioId}/plans/${planId}`, data).then(r => r?.data ?? r),

  delete: (scenarioId: string, planId: string) =>
    apiClientV2.delete(`/scenarios/${scenarioId}/plans/${planId}`),

  generate: (scenarioId: string, count = 3, strategy = 'diverse') =>
    apiClientV2.post<any>(`/scenarios/${scenarioId}/plans/generate`, { count, strategy }).then(r => r?.data ?? r),

  run: (scenarioId: string, planId: string) =>
    apiClientV2.post<any>(`/scenarios/${scenarioId}/plans/${planId}/run`).then(r => r?.data ?? r),

  compare: (scenarioId: string) =>
    apiClientV2.get<any>(`/scenarios/${scenarioId}/plans/compare`).then(r => r?.data ?? r),

  templates: () =>
    apiClientV2.get<any>(`/plans/templates`).then(r => r?.data ?? r),

  saveTemplate: (scenarioId: string, planId: string) =>
    apiClientV2.post<any>(`/scenarios/${scenarioId}/plans/${planId}/save-template`).then(r => r?.data ?? r),

  // ── Intelligence ──
  listIntel: (scenarioId: string, planId = '') =>
    apiClientV2.get<any>(`/scenarios/${scenarioId}/intelligence?plan_id=${planId}`).then(r => r?.data ?? r ?? []),

  createIntel: (scenarioId: string, data: { tick: number; text: string; plan_id?: string }) =>
    apiClientV2.post<any>(`/scenarios/${scenarioId}/intelligence`, data).then(r => r?.data ?? r),

  deleteIntel: (scenarioId: string, intelId: string) =>
    apiClientV2.delete(`/scenarios/${scenarioId}/intelligence/${intelId}`),

  parseIntel: (scenarioId: string, intelId: string) =>
    apiClientV2.post<any>(`/scenarios/${scenarioId}/intelligence/${intelId}/parse`).then(r => r?.data ?? r),

  applyIntel: (scenarioId: string, intelId: string) =>
    apiClientV2.post<any>(`/scenarios/${scenarioId}/intelligence/${intelId}/apply`).then(r => r?.data ?? r),

  // ── QA ──
  ask: (scenarioId: string, question: string, planId?: string, history?: { role: string; content: string }[]) =>
    apiClientV2.post<any>(`/scenarios/${scenarioId}/qa`, {
      question, plan_id: planId,
      conversation_history: history || [],
    }).then(r => r?.data ?? r),
}

export default plansApi
