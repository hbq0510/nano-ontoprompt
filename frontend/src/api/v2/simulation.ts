/** 推演系统 API */
import { apiClientV2 } from '@/api/client'

export interface Scenario {
  id: string
  ontology_id: string
  name: string
  description?: string
  participant_instance_ids: string[]
  initial_state: { instance_id: string; initial_properties: Record<string, unknown> }[]
  tick_interval_ms: number
  max_ticks: number
  current_tick: number
  status: 'draft' | 'running' | 'paused' | 'finished'
  loop: boolean
  created_by?: string
  created_at?: string
  updated_at?: string
}

export interface ScenarioListItem {
  id: string
  name: string
  description?: string
  status: string
  current_tick: number
  max_ticks: number
  participant_count: number
  created_at?: string
}

export interface TickData {
  id: string
  scenario_id: string
  tick: number
  instance_states: { instance_id: string; instance_name: string; object_type_id: string; properties: Record<string, unknown> }[]
  active_links: { link_id: string; link_type_id: string; source_instance_id: string; target_instance_id: string; properties: Record<string, unknown> }[]
  events?: string[]
  created_at?: string
}

export interface SimEvent {
  id: string
  scenario_id: string
  tick: number
  event_type: string
  source_instance_id?: string
  target_instance_id?: string
  description?: string
  extra?: Record<string, unknown>
  created_at?: string
}

export interface SimStepResult {
  tick: number
  events: { tick: number; event_type: string; source_instance_id?: string; description?: string; extra?: Record<string, unknown> }[]
  instance_states: Record<string, unknown>[]
  active_links: Record<string, unknown>[]
  finished: boolean
}

const simulationApi = {
  // ── Scenario CRUD ──
  // 注意: axios interceptor 已自动提取 res.data.data, 所以这里直接返回
  listScenarios: (ontologyId: string) =>
    apiClientV2.get<any>(`/ontologies/${ontologyId}/scenarios`).then(r => Array.isArray(r) ? r : (Array.isArray(r?.data) ? r.data : (r?.items ?? r ?? []))),

  getScenario: (ontologyId: string, scenarioId: string) =>
    apiClientV2.get<any>(`/ontologies/${ontologyId}/scenarios/${scenarioId}`).then(r => r?.data ?? r ?? {}),

  createScenario: (ontologyId: string, data: Partial<Scenario>) =>
    apiClientV2.post<any>(`/ontologies/${ontologyId}/scenarios`, data).then(r => r?.data ?? r),

  updateScenario: (ontologyId: string, scenarioId: string, data: Partial<Scenario>) =>
    apiClientV2.put<any>(`/ontologies/${ontologyId}/scenarios/${scenarioId}`, data).then(r => r?.data ?? r),

  deleteScenario: (ontologyId: string, scenarioId: string) =>
    apiClientV2.delete(`/ontologies/${ontologyId}/scenarios/${scenarioId}`),

  // ── 推演控制 ──
  startSimulation: (ontologyId: string, scenarioId: string) =>
    apiClientV2.post<any>(`/ontologies/${ontologyId}/scenarios/${scenarioId}/start`).then(r => r?.data ?? r),

  stepSimulation: (ontologyId: string, scenarioId: string) =>
    apiClientV2.post<any>(`/ontologies/${ontologyId}/scenarios/${scenarioId}/tick`).then(r => r?.data ?? r),

  pauseSimulation: (ontologyId: string, scenarioId: string) =>
    apiClientV2.post<any>(`/ontologies/${ontologyId}/scenarios/${scenarioId}/pause`).then(r => r?.data ?? r),

  resumeSimulation: (ontologyId: string, scenarioId: string) =>
    apiClientV2.post<any>(`/ontologies/${ontologyId}/scenarios/${scenarioId}/resume`).then(r => r?.data ?? r),

  resetSimulation: (ontologyId: string, scenarioId: string) =>
    apiClientV2.post<any>(`/ontologies/${ontologyId}/scenarios/${scenarioId}/reset`).then(r => r?.data ?? r),

  // ── 时间线 ──
  getTimeline: (ontologyId: string, scenarioId: string, fromTick = 0) =>
    apiClientV2.get<any>(`/ontologies/${ontologyId}/scenarios/${scenarioId}/timeline?from_tick=${fromTick}`).then(r => r?.data ?? r ?? []),

  getEvents: (ontologyId: string, scenarioId: string, fromTick = 0) =>
    apiClientV2.get<any>(`/ontologies/${ontologyId}/scenarios/${scenarioId}/events?from_tick=${fromTick}`).then(r => r?.data ?? r ?? []),
}

export type { Scenario as ScenarioType }
export default simulationApi
