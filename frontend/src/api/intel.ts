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
}
