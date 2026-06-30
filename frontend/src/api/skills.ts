import { apiClientV2 } from './client'
import type { Skill, SkillListItem, SkillTrigger } from '@/types/skill'

export const skillApi = {
  // CRUD
  list: (params?: { domain?: string; enabled_only?: boolean }) =>
    apiClientV2.get<SkillListItem[]>('/skills', { params }),

  create: (body: Partial<Skill>) =>
    apiClientV2.post<Skill>('/skills', body),

  get: (id: string) =>
    apiClientV2.get<Skill>(`/skills/${id}`),

  update: (id: string, body: Partial<Skill>) =>
    apiClientV2.put<Skill>(`/skills/${id}`, body),

  delete: (id: string) =>
    apiClientV2.delete(`/skills/${id}`),

  // Trigger
  trigger: (skillId: string, file: File, metadata?: Record<string, unknown>) => {
    const form = new FormData()
    form.append('file', file)
    form.append('metadata', JSON.stringify(metadata || {}))
    return apiClientV2.post<{ trigger_id: string; status: string; message: string }>(
      `/skills/${skillId}/trigger`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
  },

  listPendingTriggers: () =>
    apiClientV2.get<SkillTrigger[]>('/skills/triggers/pending'),

  confirmTrigger: (triggerId: string) =>
    apiClientV2.post<{
      trigger_id: string
      ontology_id: string
      extraction_task_id: string
      status: string
      message: string
    }>(`/skills/triggers/${triggerId}/confirm`),

  rejectTrigger: (triggerId: string) =>
    apiClientV2.post<{ trigger_id: string; status: string }>(`/skills/triggers/${triggerId}/reject`),

  getTrigger: (triggerId: string) =>
    apiClientV2.get<SkillTrigger>(`/skills/triggers/${triggerId}`),
}
