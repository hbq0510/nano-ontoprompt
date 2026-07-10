export type OntologyStatus = 'draft' | 'creating' | 'created' | 'archived'

export interface OntologyListItem {
  id: string
  name: string
  domain: string
  version: string
  status: OntologyStatus
  build_mode?: string
  entity_count: number
  relation_count: number
  created_by: string
  created_at: string
  updated_at: string
}

export interface OntologyDetail extends OntologyListItem {
  description?: string
  build_mode?: string
  created_at: string
}

export interface Entity {
  id: string
  ontology_id: string
  name_cn: string
  name_en?: string
  type?: string
  description?: string
  properties: Record<string, unknown>
  property_schema: Record<string, { type: string; unit?: string }>
  confidence: number
  version: string
  created_at: string
  updated_at: string
}

export interface LogicRule {
  id: string
  ontology_id: string
  name_cn: string
  name_en?: string
  description?: string
  formula?: string
  confidence: number
  version: string
  enabled?: boolean
  status?: string
  linked_entities: string[]
  conditions?: Array<{ field: string; op: string; value: unknown }>
  needs_review?: boolean
  created_at: string
  updated_at: string
}

export interface Action {
  id: string
  ontology_id: string
  name_cn: string
  name_en?: string
  description?: string
  execution_rule?: string
  function_code?: string
  linked_entities: string[]
  linked_logic_ids: string[]
  submission_criteria?: Array<{ field: string; op: string; value: unknown }>
  target_entity_type?: string
  needs_review?: boolean
  confidence: number
  version: string
  created_at: string
  updated_at: string
}

export interface UploadedFile {
  id: string
  ontology_id: string
  filename: string
  file_size: number
  mime_type?: string
  created_at: string
}

export interface Prompt {
  id: string
  name: string
  domain: string
  content: string
  version: string
  created_by: string
  created_at: string
  updated_at: string
}

export interface ModelConfig {
  id: string
  name: string
  config_type: 'llm' | 'ocr' | 'other'
  provider: string
  api_base?: string
  models: string[]
  options?: Record<string, unknown>
  created_by: string
  created_at: string
  updated_at: string
}

export const DOMAINS = ['军事','供应链','采购','财务','医疗','金融','法律','教育','科技','制造','能源','其他']

// ── Entity Template ─────────────────────────────────────────────────
export interface FieldDef {
  name: string
  type: 'string' | 'number' | 'select' | 'boolean' | 'text'
  required: boolean
  options: string[]
  unit: string
}

export interface EntityTemplate {
  id: string
  ontology_id: string
  type_name: string
  type_name_en?: string
  description?: string
  fields: FieldDef[]
  created_at: string
  updated_at: string
}

// ── Phase 2: ObjectType / ObjectInstance ────────────────────────────────
export interface ObjectType {
  id: string
  ontology_id: string
  name_cn: string
  name_en?: string
  description?: string
  property_schema: Record<string, { type: string; unit?: string }>
  interface_ids: string[]
  confidence: number
  version: string
  created_at: string
  updated_at: string
}

export interface ObjectInstance {
  id: string
  ontology_id: string
  object_type_id: string
  name_cn: string
  name_en?: string
  description?: string
  properties: Record<string, unknown>
  confidence: number
  version: string
  created_at: string
  updated_at: string
}

export interface OntologyInterface {
  id: string
  ontology_id: string
  name_cn: string
  name_en?: string
  description?: string
  shared_properties: Array<{ name: string; type: string; description?: string }>
  created_at: string
  updated_at: string
}

export interface LinkTypeItem {
  id: string
  ontology_id: string
  name_cn: string
  name_en?: string
  description?: string
  source_object_type_id?: string
  target_object_type_id?: string
  created_at: string
  updated_at: string
}

export interface LinkItem {
  id: string
  ontology_id: string
  link_type_id: string
  source_instance_id: string
  target_instance_id: string
  confidence: number
  created_at: string
}
