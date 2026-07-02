import { apiClient } from './client'
import type { OntologyListItem, OntologyDetail, Entity, LogicRule, Action, UploadedFile, Prompt, ModelConfig, EntityTemplate } from '@/types/ontology'

export const ontologyApi = {
  list: (params?: { name?: string; page?: number; page_size?: number }) =>
    apiClient.get<{ items: OntologyListItem[]; total: number; page: number; page_size: number }>('/ontologies', { params }),
  create: (body: { name: string; domain: string; description?: string; build_mode?: string }) =>
    apiClient.post<OntologyDetail>('/ontologies', body),
  get: (id: string) => apiClient.get<OntologyDetail>(`/ontologies/${id}`),
  update: (id: string, body: Partial<OntologyDetail>) => apiClient.put<OntologyDetail>(`/ontologies/${id}`, body),
  delete: (id: string) => apiClient.delete(`/ontologies/${id}`),
  batchDelete: (ids: string[]) => apiClient.delete('/ontologies/batch', { data: { ids } }),

  // Files
  listFiles: (oid: string) => apiClient.get<UploadedFile[]>(`/ontologies/${oid}/files`),
  deleteFile: (oid: string, fid: string) => apiClient.delete(`/ontologies/${oid}/files/${fid}`),

  // Graph
  getGraph: (oid: string) => apiClient.get<{ nodes: object[]; edges: object[]; meta: object }>(`/ontologies/${oid}/graph`),
  createRelation: (oid: string, body: object) => apiClient.post(`/ontologies/${oid}/graph/relations`, body),
  deleteRelation: (oid: string, rid: string) => apiClient.delete(`/ontologies/${oid}/graph/relations/${rid}`),

  // Entities
  listEntities: (oid: string) => apiClient.get<Entity[]>(`/ontologies/${oid}/entities`),
  createEntity: (oid: string, body: Partial<Entity>) => apiClient.post<Entity>(`/ontologies/${oid}/entities`, body),
  updateEntity: (oid: string, eid: string, body: Partial<Entity>) => apiClient.put<Entity>(`/ontologies/${oid}/entities/${eid}`, body),
  deleteEntity: (oid: string, eid: string) => apiClient.delete(`/ontologies/${oid}/entities/${eid}`),
  getEntityRelated: (oid: string, eid: string) =>
    apiClient.get<{ logic: any[]; actions: any[] }>(`/ontologies/${oid}/entities/${eid}/related`),

  // Logic
  listLogic: (oid: string) => apiClient.get<LogicRule[]>(`/ontologies/${oid}/logic`),
  createLogic: (oid: string, body: Partial<LogicRule>) => apiClient.post<LogicRule>(`/ontologies/${oid}/logic`, body),
  updateLogic: (oid: string, lid: string, body: Partial<LogicRule>) => apiClient.put<LogicRule>(`/ontologies/${oid}/logic/${lid}`, body),
  deleteLogic: (oid: string, lid: string) => apiClient.delete(`/ontologies/${oid}/logic/${lid}`),

  // Actions
  listActions: (oid: string) => apiClient.get<Action[]>(`/ontologies/${oid}/actions`),
  createAction: (oid: string, body: Partial<Action>) => apiClient.post<Action>(`/ontologies/${oid}/actions`, body),
  updateAction: (oid: string, aid: string, body: Partial<Action>) => apiClient.put<Action>(`/ontologies/${oid}/actions/${aid}`, body),
  deleteAction: (oid: string, aid: string) => apiClient.delete(`/ontologies/${oid}/actions/${aid}`),

  // Extraction
  startExtraction: (oid: string, body: { prompt_id: string; model_id: string; model_name: string; constraints?: string[] }) =>
    apiClient.post<{ task_id: string }>(`/ontologies/${oid}/execute`, body),
  getExtractionStatus: (oid: string, task_id: string) =>
    apiClient.get(`/ontologies/${oid}/execute/status?task_id=${task_id}`),

  // Templates
  listTemplates: (oid: string) => apiClient.get<EntityTemplate[]>(`/ontologies/${oid}/templates`),
  createTemplate: (oid: string, body: Partial<EntityTemplate>) => apiClient.post<EntityTemplate>(`/ontologies/${oid}/templates`, body),
  updateTemplate: (oid: string, tid: string, body: Partial<EntityTemplate>) => apiClient.put<EntityTemplate>(`/ontologies/${oid}/templates/${tid}`, body),
  deleteTemplate: (oid: string, tid: string) => apiClient.delete(`/ontologies/${oid}/templates/${tid}`),

  // Export
  exportUrl: (oid: string, format: string) => `/api/v1/ontologies/${oid}/export?format=${format}`,
}

export const promptApi = {
  list: (domain?: string) => apiClient.get<Prompt[]>('/prompts', { params: domain ? { domain } : {} }),
  getTemplates: () => apiClient.get<{ name: string; domain: string; content: string }[]>('/prompts/templates'),
  create: (body: Partial<Prompt>) => apiClient.post<Prompt>('/prompts', body),
  get: (id: string) => apiClient.get<Prompt>(`/prompts/${id}`),
  update: (id: string, body: Partial<Prompt>) => apiClient.put<Prompt>(`/prompts/${id}`, body),
  delete: (id: string) => apiClient.delete(`/prompts/${id}`),
  generateTemplate: (domain: string) =>
    apiClient.post<{ domain: string; content: string }>(`/prompts/generate-template?domain=${encodeURIComponent(domain)}&style=ontology_extraction`, {}),
}

export const modelApi = {
  list: () => apiClient.get<ModelConfig[]>('/models'),
  create: (body: Partial<ModelConfig> & { api_key?: string }) => apiClient.post<ModelConfig>('/models', body),
  get: (id: string) => apiClient.get<ModelConfig>(`/models/${id}`),
  update: (id: string, body: Partial<ModelConfig> & { api_key?: string }) => apiClient.put<ModelConfig>(`/models/${id}`, body),
  delete: (id: string) => apiClient.delete(`/models/${id}`),
  test: (id: string) => apiClient.post(`/models/${id}/test`),
}

export const settingsApi = {
  getRules: () => apiClient.get<{ rule_key: string; rule_value: string; rule_label_cn: string; rule_label_en: string; editable: boolean }[]>('/settings/rules'),
  updateRules: (rules: { rule_key: string; rule_value: string }[]) => apiClient.put('/settings/rules', rules),
  listSnapshots: () => apiClient.get<{ name: string; size: number; created_at: string; engine: string }[]>('/settings/snapshots'),
  createSnapshot: (label?: string) => apiClient.post<{ name: string; size: number; created_at: string; engine: string }>('/settings/snapshots', { label: label || null }),
  restoreSnapshot: (name: string) => apiClient.post<{ name: string; size: number; created_at: string; engine: string }>('/settings/snapshots/restore', { name }),
  deleteSnapshot: (name: string) => apiClient.delete('/settings/snapshots', { data: { name } }),
}

export const usersApi = {
  list: () => apiClient.get<{ id: string; username: string; email: string; role: string; created_at: string }[]>('/users'),
  create: (body: { username: string; email: string; password: string; role: string }) =>
    apiClient.post('/users', body),
  update: (id: string, body: { username?: string; email?: string; password?: string; role?: string }) =>
    apiClient.put(`/users/${id}`, body),
  delete: (id: string) => apiClient.delete(`/users/${id}`),
}
