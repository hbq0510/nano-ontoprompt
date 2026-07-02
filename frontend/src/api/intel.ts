import { apiClientV2 } from './client'
import type {
  IntelAssessData,
  IntelSnapshot,
  IntelInitResponse,
  IntelSubmitResponse,
  GraphData,
} from '@/types/intel'

export const intelApi = {
  init: (body?: { name?: string; description?: string }) =>
    apiClientV2.post<IntelInitResponse>('/intel-demo/init', body || {}),

  submit: (ontologyId: string, intelText: string) =>
    apiClientV2.post<IntelSubmitResponse>(`/intel-demo/${ontologyId}/submit`, {
      intel_text: intelText,
    }),

  getSnapshots: (ontologyId: string) =>
    apiClientV2.get<IntelSnapshot[]>(`/intel-demo/${ontologyId}/snapshots`),

  assess: (ontologyId: string) =>
    apiClientV2.get<IntelAssessData>(`/intel-demo/${ontologyId}/assess`),

  getGraph: (ontologyId: string) =>
    apiClientV2.get<GraphData>(`/intel-demo/${ontologyId}/graph`),

  assessQuick: (ontologyId: string, intelText: string) =>
    apiClientV2.post<IntelAssessData & {
      matched_entities: Array<{ id: string; name_cn: string; type: string; match_keyword: string }>
      triggered_rules: Array<{ id: string; name_cn: string; formula: string; linked_entities: string[] }>
      triggered_actions: Array<{ id: string; name_cn: string; execution_rule: string; function_code: string }>
      mode: string
    }>(`/intel-demo/${ontologyId}/assess-quick`, { intel_text: intelText }),

  undoLast: (ontologyId: string) =>
    apiClientV2.post<{ reverted: boolean; message: string; snapshot_label?: string; reverted_entities?: number }>(`/intel-demo/${ontologyId}/undo-last`),

  suggestRules: (ontologyId: string) =>
    apiClientV2.post<{
      suggestions: { suggested_rules: Array<{ name_cn: string; formula: string; description: string; linked_entities: string[] }>; suggested_actions: Array<{ name_cn: string; execution_rule: string; description: string; linked_entities: string[] }> }
      snapshot_count: number; message: string
    }>(`/intel-demo/${ontologyId}/suggest-rules`),

  approveRule: (ontologyId: string, rule: { name_cn: string; formula: string; description: string; linked_entities: string[] }) =>
    apiClientV2.post<{ added: boolean; rule_id?: string; message: string }>(`/intel-demo/${ontologyId}/approve-rule`, rule),

  approveAction: (ontologyId: string, action: { name_cn: string; execution_rule: string; description: string; linked_entities: string[] }) =>
    apiClientV2.post<{ added: boolean; action_id?: string; message: string }>(`/intel-demo/${ontologyId}/approve-action`, action),

  forward: (ontologyId: string, intelText: string) =>
    apiClientV2.post<{ success: boolean; message: string; webhook_url: string; payload: any }>(`/intel-demo/${ontologyId}/forward`, { intel_text: intelText }),
}
