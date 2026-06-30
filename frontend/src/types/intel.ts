export interface IntelSnapshot {
  id: string
  label: string
  intel_text: string
  entity_count: number
  relation_count: number
  danger_score: number
  danger_level: 'low' | 'medium' | 'high' | 'critical'
  recommendations: string[]
  status: 'extracting' | 'completed' | 'failed'
  created_at: string
}

export interface GraphData {
  nodes: Array<{
    id: string
    labels: string[]
    properties: Record<string, unknown>
  }>
  edges: Array<{
    id: string
    source: string
    target: string
    type: string
  }>
  neo4j_available: boolean
  fallback?: string
}

export interface IntelAssessData {
  ontology_id: string
  ontology_name: string
  danger_level: string
  danger_score: number
  recommendations: string[]
  entity_count: number
  relation_count: number
  snapshots: IntelSnapshot[]
  graph: GraphData
}

export interface IntelInitResponse {
  ontology_id: string
  name: string
}

export interface IntelSubmitResponse {
  snapshot_id: string
  task_id: string
  status: string
}

export const DANGER_LABELS: Record<string, string> = {
  low: '低威胁',
  medium: '中等威胁',
  high: '高威胁',
  critical: '严重威胁',
}

export const DANGER_COLORS: Record<string, string> = {
  low: '#10b981',
  medium: '#f59e0b',
  high: '#f97316',
  critical: '#ef4444',
}
