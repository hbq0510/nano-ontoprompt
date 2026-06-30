export interface Skill {
  id: string
  name: string
  description?: string
  domain: string
  accepted_input_types: string[]
  prompt_id?: string | null
  model_id?: string | null
  ontology_name_pattern: string
  prebuilt_entities: string[]
  enabled: boolean
  created_by: string
  created_at: string
  updated_at: string
}

export interface SkillListItem {
  id: string
  name: string
  description?: string
  domain: string
  enabled: boolean
  created_by: string
  created_at: string
  updated_at: string
}

export interface SkillTrigger {
  id: string
  skill_id: string
  skill_name?: string
  status: 'pending' | 'confirmed' | 'rejected' | 'executing' | 'completed' | 'failed'
  input_file_name: string
  input_metadata: Record<string, unknown>
  ontology_id?: string | null
  extraction_task_id?: string | null
  error?: string | null
  created_at: string
  updated_at: string
}

export const SKILL_DOMAINS = [
  '军事', '供应链', '采购', '财务', '医疗', '金融',
  '法律', '教育', '科技', '制造', '能源', '其他',
]

export const INPUT_TYPES = [
  { value: 'image/*', label: '图像文件' },
  { value: 'image/png', label: 'PNG' },
  { value: 'image/jpeg', label: 'JPEG' },
  { value: 'image/tiff', label: 'TIFF' },
  { value: 'text/plain', label: '文本文件' },
  { value: 'application/pdf', label: 'PDF' },
  { value: 'application/json', label: 'JSON' },
  { value: 'text/csv', label: 'CSV' },
  { value: 'text/markdown', label: 'Markdown' },
]
