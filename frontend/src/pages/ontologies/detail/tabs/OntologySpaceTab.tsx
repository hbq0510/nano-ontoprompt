import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ontologyApi } from '@/api/ontologies'
import { ChevronRight, ChevronDown, Plus, Trash2, Pencil, X, Save, Code2, Zap, Play, Terminal, Circle } from 'lucide-react'
import type { ObjectType, ObjectInstance } from '@/types/ontology'

interface SchemaField { key: string; name: string; type: string; unit: string }
interface ObjRule { id: string; name_cn: string; description?: string; python_code?: string; object_type_id?: string; object_instance_id?: string }
interface ObjAction { id: string; name_cn: string; description?: string; python_code?: string; object_type_id?: string; object_instance_id?: string; object_rule_id?: string }

type TreeNode = { id: string; name_cn: string; name_en?: string; description?: string; property_schema: any; isType: boolean; instance?: ObjectInstance; children: TreeNode[]; depth: number }

export default function OntologySpaceTab({ ontologyId }: { ontologyId: string }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [editId, setEditId] = useState<string | null>(null)
  const [newChildParentId, setNewChildParentId] = useState<string | null>(null)
  const [form, setForm] = useState({ name_cn: '', name_en: '', description: '' })
  const [fields, setFields] = useState<SchemaField[]>([])
  const [showNew, setShowNew] = useState(false)
  const [error, setError] = useState('')
  const [showInstForm, setShowInstForm] = useState<string | null>(null)
  const [editInstId, setEditInstId] = useState<string | null>(null)
  const [instForm, setInstForm] = useState({ name_cn: '', name_en: '', description: '' })
  const [instProps, setInstProps] = useState<Record<string, string>>({})
  const [showRuleEditor, setShowRuleEditor] = useState<{targetType:'type'|'instance';targetId:string;editId?:string}|null>(null)
  const [ruleForm, setRuleForm] = useState({name_cn:'',description:'',python_code:'def check(context: dict) -> dict:\n    return {"passed": True, "message": "ok"}\n'})
  const [showActionEditor, setShowActionEditor] = useState<{targetType:'type'|'instance';targetId:string;editId?:string}|null>(null)
  const [actionForm, setActionForm] = useState({name_cn:'',description:'',python_code:'def execute(context: dict) -> dict:\n    return {"status": "done"}\n'})
  const [ruleFilterType, setRuleFilterType] = useState('all')
  const [ruleFilterId, setRuleFilterId] = useState('')
  const [showLinkForm, setShowLinkForm] = useState(false)
  const [editLinkId, setEditLinkId] = useState<string | null>(null)
  const [linkForm, setLinkForm] = useState({name_cn:'',name_en:'',description:'',source_object_type_id:'',target_object_type_id:'',property_schema:'{}'})
  const [linkFields, setLinkFields] = useState<SchemaField[]>([])

  const { data: types = [] } = useQuery({ queryKey: ['object-types', ontologyId], queryFn: () => ontologyApi.listObjectTypes(ontologyId) as Promise<ObjectType[]>, staleTime: 30_000 })
  const { data: instances = [] } = useQuery({ queryKey: ['object-instances', ontologyId], queryFn: () => ontologyApi.listInstances(ontologyId) as Promise<ObjectInstance[]>, staleTime: 30_000 })
  const { data: linkTypes = [] } = useQuery({ queryKey: ['link-types', ontologyId], queryFn: () => ontologyApi.listLinkTypes(ontologyId) as Promise<any[]>, staleTime: 60_000 })
  const { data: links = [] } = useQuery({ queryKey: ['links-list', ontologyId], queryFn: () => ontologyApi.listLinks(ontologyId) as Promise<any[]>, staleTime: 15_000 })
  const { data: rules = [] } = useQuery({ queryKey: ['object-rules', ontologyId], queryFn: () => ontologyApi.listRules(ontologyId).then((r:any)=>Array.isArray(r)?r:(r?.data||[])), staleTime: 30_000 })
  const { data: actions = [] } = useQuery({ queryKey: ['object-actions', ontologyId], queryFn: () => ontologyApi.listActionsV2(ontologyId).then((r:any)=>Array.isArray(r)?r:(r?.data||[])), staleTime: 30_000 })

  // Build tree: ObjectTypes with parent_id hierarchy, instances under their type
  const tree = useMemo(() => {
    const allTypes = types as ObjectType[]
    const instByType: Record<string, ObjectInstance[]> = {}
    ;(instances as ObjectInstance[]).forEach(i => { if (!instByType[i.object_type_id]) instByType[i.object_type_id] = []; instByType[i.object_type_id].push(i) })

    const nodes: Record<string, TreeNode> = {}
    allTypes.forEach(t => { nodes[t.id] = { id: t.id, name_cn: t.name_cn, name_en: t.name_en, description: t.description, property_schema: t.property_schema || {}, isType: true, children: [], depth: 0 } })
    // Attach instances under types
    Object.entries(instByType).forEach(([tid, ois]) => {
      if (nodes[tid]) ois.forEach(oi => nodes[tid].children.push({ id: oi.id, name_cn: oi.name_cn, name_en: oi.name_en, description: oi.description, property_schema: {}, isType: false, instance: oi, children: [], depth: 1 }))
    })
    // Build parent-child for types
    const roots: TreeNode[] = []
    allTypes.forEach(t => {
      const pid = (t as any).parent_id
      if (pid && nodes[pid]) { nodes[pid].children.unshift(nodes[t.id]); nodes[t.id].depth = nodes[pid].depth + 1 }
      else if (!nodes[t.id]._placed) { roots.push(nodes[t.id]); (nodes[t.id] as any)._placed = true }
    })
    // dedupe: if a node was added as child, don't also show as root
    const seen = new Set<string>()
    const result: TreeNode[] = []
    allTypes.forEach(t => { const pid = (t as any).parent_id; if (!pid || !nodes[pid]) result.push(nodes[t.id]) })
    // Fix depths for nested
    function fixDepth(n: TreeNode, d: number) { n.depth = d; n.children.forEach(c => fixDepth(c, d + 1)) }
    result.forEach(r => fixDepth(r, 0))
    return result
  }, [types, instances])

  function flatten(nodes: TreeNode[], expanded: Set<string>): TreeNode[] {
    const r: TreeNode[] = []
    function w(list: TreeNode[]) { list.forEach(n => { r.push(n); if (expanded.has(n.id)) w(n.children) }) }
    w(nodes); return r
  }
  const visible = useMemo(() => flatten(tree, expanded), [tree, expanded])

  // Group rules/actions by type and instance
  const rulesByType = useMemo(() => { const m:Record<string,ObjRule[]>={};rules.forEach((r:ObjRule)=>{if(r.object_type_id&&!r.object_instance_id){if(!m[r.object_type_id])m[r.object_type_id]=[];m[r.object_type_id].push(r)}});return m },[rules])
  const rulesByInst = useMemo(() => { const m:Record<string,ObjRule[]>={};rules.forEach((r:ObjRule)=>{if(r.object_instance_id){if(!m[r.object_instance_id])m[r.object_instance_id]=[];m[r.object_instance_id].push(r)}});return m },[rules])
  const actionsByType = useMemo(() => { const m:Record<string,ObjAction[]>={};actions.forEach((a:ObjAction)=>{if(a.object_type_id&&!a.object_instance_id){if(!m[a.object_type_id])m[a.object_type_id]=[];m[a.object_type_id].push(a)}});return m },[actions])
  const actionsByInst = useMemo(() => { const m:Record<string,ObjAction[]>={};actions.forEach((a:ObjAction)=>{if(a.object_instance_id){if(!m[a.object_instance_id])m[a.object_instance_id]=[];m[a.object_instance_id].push(a)}});return m },[actions])

  // ── Mutations ──
  const createMut = useMutation({ mutationFn: (d:any)=>{console.log('CREATE CALLED',d);return ontologyApi.createObjectType(ontologyId,d)}, onSuccess:(r:any)=>{console.log('CREATE OK',r);qc.invalidateQueries({queryKey:['object-types',ontologyId]});setShowNew(false);setEditId(null);setNewChildParentId(null)}, onError:(e:any)=>{console.error('CREATE ERR',e);setError(String(e?.response?.data?.detail||e?.response?.status||e?.message||e))} })
  const updateMut = useMutation({ mutationFn:({id,data}:{id:string;data:any})=>ontologyApi.updateObjectType(ontologyId,id,data), onSuccess:()=>{qc.invalidateQueries({queryKey:['object-types',ontologyId]});setEditId(null)}, onError:(e:any)=>{setError(e?.response?.data?.detail?.message||e?.message||'更新失败')} })
  const deleteMut = useMutation({ mutationFn:(id:string)=>ontologyApi.deleteObjectType(ontologyId,id), onSuccess:()=>qc.invalidateQueries({queryKey:['object-types',ontologyId]}) })
  const deleteInstMut = useMutation({ mutationFn:(id:string)=>ontologyApi.deleteInstance(ontologyId,id), onSuccess:()=>qc.invalidateQueries({queryKey:['object-instances',ontologyId]}) })
  const createInstMut = useMutation({ mutationFn:(d:any)=>ontologyApi.createInstance(ontologyId,d), onSuccess:()=>{qc.invalidateQueries({queryKey:['object-instances',ontologyId]});setShowInstForm(null)} })
  const updateInstMut = useMutation({ mutationFn:({id,data}:{id:string;data:any})=>ontologyApi.updateInstance(ontologyId,id,data), onSuccess:()=>{qc.invalidateQueries({queryKey:['object-instances',ontologyId]});setEditInstId(null)} })
  const createLinkMut = useMutation({ mutationFn:(d:any)=>ontologyApi.createLinkType(ontologyId,d), onSuccess:()=>{qc.invalidateQueries({queryKey:['link-types',ontologyId]});setShowLinkForm(false);setEditLinkId(null)} })
  const updateLinkMut = useMutation({ mutationFn:({id,data}:{id:string;data:any})=>ontologyApi.updateLinkType(ontologyId,id,data), onSuccess:()=>{qc.invalidateQueries({queryKey:['link-types',ontologyId]});setShowLinkForm(false);setEditLinkId(null)} })
  const deleteLinkMut = useMutation({ mutationFn:(id:string)=>ontologyApi.deleteLinkType(ontologyId,id), onSuccess:()=>qc.invalidateQueries({queryKey:['link-types',ontologyId]}) })
  const deleteLinkInstMut = useMutation({ mutationFn:(id:string)=>ontologyApi.deleteLink(ontologyId,id), onSuccess:()=>qc.invalidateQueries({queryKey:['links-list',ontologyId]}) })
  const createRuleMut = useMutation({ mutationFn:(d:any)=>ontologyApi.createRule(ontologyId,d), onSuccess:()=>{qc.invalidateQueries({queryKey:['object-rules',ontologyId]});setShowRuleEditor(null)}, onError:(e:any)=>alert('创建失败: '+String(e)) })
  const updateRuleMut = useMutation({ mutationFn:({id,data}:{id:string;data:any})=>ontologyApi.updateRule(ontologyId,id,data), onSuccess:()=>{qc.invalidateQueries({queryKey:['object-rules',ontologyId]});setShowRuleEditor(null)}, onError:(e:any)=>alert('更新失败: '+String(e))})
  const createActionMut = useMutation({ mutationFn:(d:any)=>ontologyApi.createActionV2(ontologyId,d), onSuccess:()=>{qc.invalidateQueries({queryKey:['object-actions',ontologyId]});setShowActionEditor(null)} })
  const updateActionMut = useMutation({ mutationFn:({id,data}:{id:string;data:any})=>ontologyApi.updateActionV2(ontologyId,id,data), onSuccess:()=>{qc.invalidateQueries({queryKey:['object-actions',ontologyId]});setShowActionEditor(null)} })
  const deleteRuleMut = useMutation({ mutationFn:(id:string)=>ontologyApi.deleteRule(ontologyId,id), onSuccess:()=>qc.invalidateQueries({queryKey:['object-rules',ontologyId]}) })
  const deleteActionMut = useMutation({ mutationFn:(id:string)=>ontologyApi.deleteActionV2(ontologyId,id), onSuccess:()=>qc.invalidateQueries({queryKey:['object-actions',ontologyId]}) })

  function buildSchema() { const s:Record<string,{type:string;unit?:string}>={}; fields.forEach(f=>{if(f.name.trim())s[f.name.trim()]={type:f.type,unit:f.unit||undefined}}); return s }
  function openNew() { setError(''); setShowNew(true); setEditId(null); setNewChildParentId(null); setForm({name_cn:'',name_en:'',description:''}); setFields([]) }
  function openEdit(t:ObjectType) { setError(''); setEditId(t.id); setShowNew(false); setNewChildParentId(null); setForm({name_cn:t.name_cn,name_en:t.name_en||'',description:t.description||''}); const fs:SchemaField[]=[];let i=0;Object.entries(t.property_schema||{}).forEach(([n,d])=>{fs.push({key:`f-${i++}`,name:n,type:(d as any).type||'string',unit:(d as any).unit||''})}); setFields(fs) }
  function openNewChild(pid:string) { setError(''); setNewChildParentId(pid); setShowNew(false); setEditId(null); setForm({name_cn:'',name_en:'',description:''}); setFields([]) }

  function addField() { setFields(p=>[...p,{key:`f-${Date.now()}`,name:'',type:'string',unit:''}]) }
  function updateField(key:string,patch:Partial<SchemaField>) { setFields(prev=>prev.map(f=>f.key===key?{...f,...patch}:f)) }
  function removeField(key:string) { setFields(prev=>prev.filter(f=>f.key!==key)) }

  const editingTitle = editId ? '编辑本体' : (newChildParentId ? '新增子类' : '新增本体')

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-bold text-gray-900">本体空间树</h2>
        <p className="text-sm text-gray-500 mt-0.5">按类型组织实体、关系、属性、动作与规则。</p>
      </div>

      {/* ═══ 1. 蓝色 — 实体类型 ═══ */}
      <div className="bg-white border rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b">
          <div className="flex items-center gap-2"><Circle size={10} className="text-blue-500 fill-blue-500" /><span className="font-semibold text-sm text-gray-800">本体</span><span className="text-xs text-gray-400">({(types as ObjectType[]).length})</span></div>
          <button onClick={openNew} className="px-3 py-1.5 border rounded-lg text-xs text-gray-600 hover:bg-gray-50 flex items-center gap-1"><Plus size={12} /> 新增</button>
        </div>
        <div>
          {tree.length === 0 ? <div className="px-5 py-8 text-center text-sm text-gray-400">暂无本体，点击右上角「新增」创建</div> : (
            visible.map(node => {
              const isType = node.isType
              const hasChildren = node.children.length > 0
              const isExpanded = expanded.has(node.id)
              return (
                <div key={node.id} className={`flex items-center border-t hover:bg-gray-50 group ${!isType?'bg-gray-50/50':''}`} style={{paddingLeft:`${16+node.depth*24}px`}}>
                  <button onClick={()=>{if(!hasChildren)return;const n=new Set(expanded);isExpanded?n.delete(node.id):n.add(node.id);setExpanded(n)}} className="p-1.5 text-gray-400 hover:text-gray-600">
                    {hasChildren?(isExpanded?<ChevronDown size={14}/>:<ChevronRight size={14}/>):<span className="w-3.5 inline-block"/>}
                  </button>
                  {(() => {
                    if (isType) {
                      return (<span className="flex-1 py-2.5 pr-2 truncate text-sm font-medium text-blue-600 hover:text-blue-800 hover:underline cursor-pointer"
                        onClick={(e: any) => { e.stopPropagation(); navigate(`/ontologies/${ontologyId}/types/${node.id}`) }}>{node.name_cn}</span>)
                    } else if (node.instance) {
                      return (<span className="flex-1 py-2.5 pr-2 truncate text-sm text-blue-600 hover:text-blue-800 hover:underline cursor-pointer"
                        onClick={(e: any) => { e.stopPropagation(); navigate(`/ontologies/${ontologyId}/types/${node.instance.object_type_id}/instances/${node.id}`) }}>{node.name_cn}</span>)
                    } else {
                      return (<span className="flex-1 py-2.5 pr-2 truncate text-sm text-gray-700">{node.name_cn}</span>)
                    }
                  })()}
                  {isType && Object.entries(node.property_schema||{}).slice(0,3).map(([k])=>(<span key={k} className="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded mr-1 hidden sm:inline">{k}</span>))}
                  {/* 规则/动作计数 */}
                  {isType && (rulesByType[node.id]||[]).length > 0 && <span className="text-[10px] text-purple-500 mr-1">◇{(rulesByType[node.id]||[]).length}</span>}
                  {isType && (actionsByType[node.id]||[]).length > 0 && <span className="text-[10px] text-amber-500 mr-1">⚡{(actionsByType[node.id]||[]).length}</span>}
                  {!isType && (rulesByInst[node.id]||[]).length > 0 && <span className="text-[10px] text-purple-500 mr-1">◇{(rulesByInst[node.id]||[]).length}</span>}
                  {!isType && (actionsByInst[node.id]||[]).length > 0 && <span className="text-[10px] text-amber-500 mr-1">⚡{(actionsByInst[node.id]||[]).length}</span>}
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity pr-3 flex-shrink-0">
                    {isType && <button onClick={()=>{setShowInstForm(node.id);setInstForm({name_cn:'',name_en:'',description:''});const schema=node.property_schema||{};const vals:Record<string,string>={};Object.keys(schema).forEach(k=>{vals[k]=''});setInstProps(vals)}} className="text-xs text-green-600 hover:bg-green-50 px-2 py-1 rounded">+实体</button>}
                    {isType && <button onClick={()=>{setShowRuleEditor({targetType:'type',targetId:node.id});setRuleForm({name_cn:'',description:'',python_code:'def check(context: dict) -> dict:\n    return {"passed": True, "message": "ok"}\n'})}} className="text-xs text-purple-600 hover:bg-purple-50 px-2 py-1 rounded">+规则</button>}
                    {isType && <button onClick={()=>{setShowActionEditor({targetType:'type',targetId:node.id});setActionForm({name_cn:'',description:'',python_code:'def execute(context: dict) -> dict:\n    return {"status": "done"}\n'})}} className="text-xs text-amber-600 hover:bg-amber-50 px-2 py-1 rounded">+动作</button>}
                    {isType && <button onClick={()=>openEdit(node as any)} className="text-xs text-gray-500 hover:bg-gray-100 px-2 py-1 rounded">编辑</button>}
                    {isType && <button onClick={()=>{if(confirm(`删除本体"${node.name_cn}"及下属所有实体？`))deleteMut.mutate(node.id)}} className="text-xs text-red-500 hover:bg-red-50 px-2 py-1 rounded">删除</button>}
                    {!isType && <button onClick={()=>{setShowRuleEditor({targetType:'instance',targetId:node.id});setRuleForm({name_cn:'',description:'',python_code:'def check(context: dict) -> dict:\n    return {"passed": True, "message": "ok"}\n'})}} className="text-xs text-purple-600 hover:bg-purple-50 px-2 py-1 rounded">+规则</button>}
                    {!isType && <button onClick={()=>{setShowActionEditor({targetType:'instance',targetId:node.id});setActionForm({name_cn:'',description:'',python_code:'def execute(context: dict) -> dict:\n    return {"status": "done"}\n'})}} className="text-xs text-amber-600 hover:bg-amber-50 px-2 py-1 rounded">+动作</button>}
                    {!isType && <button onClick={()=>{setEditInstId(node.id);setInstForm({name_cn:node.name_cn,name_en:node.name_en||'',description:node.description||''});const vals:Record<string,string>={};Object.entries(node.instance?.properties||{}).forEach(([k,v])=>{vals[k]=String(v??'')});setInstProps(vals)}} className="text-xs text-gray-500 hover:bg-gray-100 px-2 py-1 rounded">编辑</button>}
                    {!isType && <button onClick={()=>{if(confirm(`删除实体"${node.name_cn}"？`))deleteInstMut.mutate(node.id)}} className="text-xs text-red-500 hover:bg-red-50 px-2 py-1 rounded">删除</button>}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* ═══ 2. 绿色 — 关系类型 ═══ */}
      <div className="bg-white border rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b">
          <div className="flex items-center gap-2"><Circle size={10} className="text-green-500 fill-green-500" /><span className="font-semibold text-sm text-gray-800">关系类型</span><span className="text-xs text-gray-400">({(linkTypes as any[]).length})</span></div>
          <button onClick={() => { setShowLinkForm(true); setEditLinkId(null); setLinkForm({name_cn:'',name_en:'',description:'',source_object_type_id:'',target_object_type_id:'',property_schema:'{}'}); setLinkFields([]) }}
            className="px-3 py-1.5 border rounded-lg text-xs text-gray-600 hover:bg-gray-50 flex items-center gap-1"><Plus size={12} /> 新增</button>
        </div>
        <div>
          {(linkTypes as any[]).length===0?<div className="px-5 py-8 text-center text-sm text-gray-400">暂无关系类型</div>:(
            (linkTypes as any[]).map((lt:any)=>{
            const srcName = (types as ObjectType[]).find(t=>t.id===lt.source_object_type_id)?.name_cn || ''
            const tgtName = (types as ObjectType[]).find(t=>t.id===lt.target_object_type_id)?.name_cn || ''
            return (<div key={lt.id} className="flex items-center px-5 py-2.5 border-t hover:bg-gray-50 group">
              <span className="text-sm text-gray-800 font-mono flex-shrink-0">{lt.name_cn||lt.name_en}</span>
              {(srcName||tgtName) && <span className="text-[10px] text-gray-400 ml-2">{srcName||'?'} → {tgtName||'?'}</span>}
              {Object.entries(lt.property_schema||{}).slice(0,3).map(([k]:[string,any])=>(
                <span key={k} className="text-[10px] bg-green-50 text-green-600 px-1.5 py-0.5 rounded ml-1">{k}</span>
              ))}
              <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity ml-auto">
                <button onClick={() => { setShowLinkForm(true); setEditLinkId(lt.id); setLinkForm({name_cn:lt.name_cn||'',name_en:lt.name_en||'',description:lt.description||'',source_object_type_id:lt.source_object_type_id||'',target_object_type_id:lt.target_object_type_id||'',property_schema:JSON.stringify(lt.property_schema||{})}); const fs:SchemaField[]=[];let i=0;Object.entries(lt.property_schema||{}).forEach(([n,d]:[string,any])=>{fs.push({key:`lf-${i++}`,name:n,type:d.type||'string',unit:d.unit||''})});setLinkFields(fs) }} className="text-xs text-gray-500 hover:bg-gray-100 px-2 py-1 rounded">编辑</button>
                <button onClick={()=>{if(confirm(`删除"${lt.name_cn||lt.name_en}"？`))deleteLinkMut.mutate(lt.id)}} className="text-xs text-red-500 hover:bg-red-50 px-2 py-1 rounded">删除</button>
              </div></div>)})
          )}
        </div>
      </div>

      {/* ═══ 3. 青色 — 关系实例 (Link) ═══ */}
      <div className="bg-white border rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b">
          <div className="flex items-center gap-2"><Circle size={10} className="text-cyan-500 fill-cyan-500" /><span className="font-semibold text-sm text-gray-800">关系实例</span><span className="text-xs text-gray-400">({(links as any[]).length} 条连线)</span></div>
        </div>
        <div>
          {(links as any[]).length === 0 ? (
            <div className="px-5 py-8 text-center text-sm text-gray-400">暂无关系实例，运行规则触发生成</div>
          ) : (
            (links as any[]).map((l: any) => {
              const srcInst = (instances as ObjectInstance[]).find(i => i.id === l.source_instance_id)
              const tgtInst = (instances as ObjectInstance[]).find(i => i.id === l.target_instance_id)
              const ltName = (linkTypes as any[]).find(lt => lt.id === l.link_type_id)?.name_cn || l.link_type_id?.slice(0,8)
              return (
                <div key={l.id} className="flex items-center px-5 py-2.5 border-t hover:bg-gray-50 group">
                  <span className="text-sm text-gray-700">{srcInst?.name_cn || l.source_instance_id?.slice(0,8)}</span>
                  <span className="text-[10px] text-cyan-600 bg-cyan-50 px-1.5 py-0.5 rounded mx-2 font-mono">—{ltName}→</span>
                  <span className="text-sm text-gray-700">{tgtInst?.name_cn || l.target_instance_id?.slice(0,8)}</span>
                  {Object.entries(l.properties||{}).slice(0,3).map(([k,v]:[string,any])=>(
                    <span key={k} className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded ml-1 font-mono">{k}={String(v)}</span>
                  ))}
                  <button onClick={() => { if (confirm(`删除此连线？`)) deleteLinkInstMut.mutate(l.id) }}
                    className="text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 ml-auto"><Trash2 size={14} /></button>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* ═══ 4. 橙色 — 属性类型 ═══ */}
      <div className="bg-white border rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b">
          <div className="flex items-center gap-2"><Circle size={10} className="text-orange-500 fill-orange-500" /><span className="font-semibold text-sm text-gray-800">属性类型</span></div>
          <button className="px-3 py-1.5 border rounded-lg text-xs text-gray-600 hover:bg-gray-50 flex items-center gap-1"><Plus size={12} /> 新增</button>
        </div>
        <div className="px-5 py-8 text-center text-sm text-gray-400">属性类型通过实体类型的 property_schema 定义，无需单独创建。</div>
      </div>

      {/* ═══ 4. 紫色 — 规则与动作（筛选视图） ═══ */}
      {(() => {
        const filterType = ruleFilterType, setFilterType = setRuleFilterType
        const filterId = ruleFilterId, setFilterId = setRuleFilterId
        // Build filter options from types and instances
        const typeOptions = (types as ObjectType[]).map(t => ({ id: t.id, name: t.name_cn, kind: '本体' }))
        const instOptions = (instances as ObjectInstance[]).map(i => ({ id: i.id, name: i.name_cn, kind: '实体', parentTypeName: (types as ObjectType[]).find(t => t.id === i.object_type_id)?.name_cn || '' }))
        const allOptions = [...typeOptions, ...instOptions]

        const filteredRules = rules.filter((r: ObjRule) => {
          if (filterType === 'all') return true
          if (filterType === 'type' && r.object_type_id && !r.object_instance_id) return !filterId || r.object_type_id === filterId
          if (filterType === 'instance' && r.object_instance_id) return !filterId || r.object_instance_id === filterId
          if (filterType === 'specific' && filterId) return r.object_type_id === filterId || r.object_instance_id === filterId
          return true
        })
        const filteredActions = actions.filter((a: ObjAction) => {
          if (filterType === 'all') return true
          if (filterType === 'type' && a.object_type_id && !a.object_instance_id) return !filterId || a.object_type_id === filterId
          if (filterType === 'instance' && a.object_instance_id) return !filterId || a.object_instance_id === filterId
          if (filterType === 'specific' && filterId) return a.object_type_id === filterId || a.object_instance_id === filterId
          return true
        })

        function getTargetLabel(r: ObjRule | ObjAction) {
          if (r.object_instance_id) {
            const inst = (instances as ObjectInstance[]).find(i => i.id === r.object_instance_id)
            const typeName = (types as ObjectType[]).find(t => t.id === r.object_type_id)?.name_cn || ''
            return `实体: ${inst?.name_cn || r.object_instance_id.slice(0,8)} (${typeName})`
          }
          if (r.object_type_id) {
            const t = (types as ObjectType[]).find(t => t.id === r.object_type_id)
            return `本体: ${t?.name_cn || r.object_type_id.slice(0,8)}`
          }
          return '全局'
        }

        return (
          <div className="bg-white border rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b">
              <div className="flex items-center gap-2"><Circle size={10} className="text-purple-500 fill-purple-500" /><span className="font-semibold text-sm text-gray-800">规则与动作</span><span className="text-xs text-gray-400">({filteredRules.length} 规则 · {filteredActions.length} 动作 {filterType !== 'all' ? '— 已筛选' : ''})</span></div>
              <div className="flex items-center gap-2">
                <select value={filterType} onChange={e => { setFilterType(e.target.value); setFilterId('') }}
                  className="border rounded-lg px-2 py-1.5 text-xs text-gray-600">
                  <option value="all">全部</option>
                  <option value="type">本体层</option>
                  <option value="instance">实体层</option>
                  <option value="specific">指定对象</option>
                </select>
                {filterType === 'specific' && (
                  <select value={filterId} onChange={e => setFilterId(e.target.value)}
                    className="border rounded-lg px-2 py-1.5 text-xs text-gray-600 max-w-[160px]">
                    <option value="">选择对象</option>
                    <optgroup label="─ 本体 ─">
                      {typeOptions.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
                    </optgroup>
                    <optgroup label="─ 实体 ─">
                      {instOptions.map(o => <option key={o.id} value={o.id}>{o.name} ({o.parentTypeName})</option>)}
                    </optgroup>
                  </select>
                )}
              </div>
            </div>
            <div>
              {filteredRules.length === 0 && filteredActions.length === 0 ? (
                <div className="px-5 py-8 text-center text-sm text-gray-400">
                  {filterType !== 'all' ? '筛选结果为空' : '暂无规则或动作，在本体/实体行中点击 [+规则] 或 [+动作] 创建'}
                </div>
              ) : (
                <>
                  {filteredRules.map((r: ObjRule) => (
                    <div key={r.id} className="flex items-center px-5 py-2.5 border-t hover:bg-gray-50 group">
                      <Code2 size={12} className="text-purple-500 mr-2 flex-shrink-0" />
                      <span className="text-sm text-gray-800 w-40 truncate flex-shrink-0">{r.name_cn}</span>
                      <span className="text-[10px] text-gray-400 ml-2 flex-shrink-0">{getTargetLabel(r)}</span>
                      {r.description && <span className="text-xs text-gray-400 truncate max-w-[200px] ml-2">— {r.description}</span>}
                      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity ml-auto">
                        <button onClick={() => { setShowRuleEditor({ targetType: r.object_instance_id ? 'instance' : 'type', targetId: (r.object_instance_id || r.object_type_id)!, editId: r.id }); setRuleForm({ name_cn: r.name_cn, description: r.description || '', python_code: r.python_code || '' }) }}
                          className="text-xs text-gray-500 hover:bg-gray-100 px-2 py-1 rounded">编辑</button>
                        <button onClick={() => { if (confirm(`删除规则"${r.name_cn}"？`)) deleteRuleMut.mutate(r.id) }}
                          className="text-xs text-red-500 hover:bg-red-50 px-2 py-1 rounded">删除</button>
                      </div>
                    </div>
                  ))}
                  {filteredActions.map((a: ObjAction) => (
                    <div key={a.id} className="flex items-center px-5 py-2.5 border-t hover:bg-gray-50 group">
                      <Zap size={12} className="text-amber-500 mr-2 flex-shrink-0" />
                      <span className="text-sm text-gray-800 w-40 truncate flex-shrink-0">{a.name_cn}</span>
                      <span className="text-[10px] text-gray-400 ml-2 flex-shrink-0">{getTargetLabel(a)}</span>
                      {a.description && <span className="text-xs text-gray-400 truncate max-w-[200px] ml-2">— {a.description}</span>}
                      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity ml-auto">
                        <button onClick={() => { setShowActionEditor({ targetType: a.object_instance_id ? 'instance' : 'type', targetId: (a.object_instance_id || a.object_type_id)!, editId: a.id }); setActionForm({ name_cn: a.name_cn, description: a.description || '', python_code: a.python_code || '' }) }}
                          className="text-xs text-gray-500 hover:bg-gray-100 px-2 py-1 rounded">编辑</button>
                        <button onClick={() => { if (confirm(`删除动作"${a.name_cn}"？`)) deleteActionMut.mutate(a.id) }}
                          className="text-xs text-red-500 hover:bg-red-50 px-2 py-1 rounded">删除</button>
                      </div>
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>
        )
      })()}

      {/* ── 实体 创建/编辑 弹窗 ── */}
      {(showInstForm || editInstId) && (() => {
        const isEdit = !!editInstId
        const inst = isEdit ? (instances as ObjectInstance[]).find(i => i.id === editInstId) : null
        const typeId = isEdit ? inst?.object_type_id || '' : showInstForm || ''
        const schema = (types as ObjectType[]).find(t => t.id === typeId)?.property_schema || {}
        const typeName = (types as ObjectType[]).find(t => t.id === typeId)?.name_cn || ''
        const close = () => { setShowInstForm(null); setEditInstId(null) }
        const buildProps = () => {
          const props: any = {}
          Object.entries(instProps).forEach(([k, v]) => {
            const def = (schema as any)[k]
            if (def?.type === 'number') { const n = parseFloat(v); if (!isNaN(n)) props[k] = n; else if (v) props[k] = v }
            else if (v) props[k] = v
          })
          return props
        }
        return (
          <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={close}>
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-xl max-h-[75vh] overflow-auto m-4" onClick={e => e.stopPropagation()}>
              <div className="p-5 space-y-4">
                <div className="flex items-center justify-between"><h3 className="font-semibold text-gray-800">{isEdit ? '编辑实体' : '新增实体'} — {typeName}</h3><button onClick={close} className="text-gray-400 hover:text-gray-600"><X size={18} /></button></div>
                <input value={instForm.name_cn} onChange={e => setInstForm({ ...instForm, name_cn: e.target.value })} placeholder="实体中文名 *" className="w-full border rounded-lg px-3 py-2 text-sm" />
                <input value={instForm.name_en} onChange={e => setInstForm({ ...instForm, name_en: e.target.value })} placeholder="实体英文名" className="w-full border rounded-lg px-3 py-2 text-sm" />
                <input value={instForm.description} onChange={e => setInstForm({ ...instForm, description: e.target.value })} placeholder="描述" className="w-full border rounded-lg px-3 py-2 text-sm" />
                {Object.keys(schema as any).length > 0 && (
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(schema as any).map(([name, def]: [string, any]) => (
                      <div key={name}><label className="block text-[10px] text-gray-500 mb-0.5">{name}{def.unit ? ` (${def.unit})` : ''}</label>
                        {def.type === 'boolean' ? (
                          <select value={instProps[name] || ''} onChange={e => setInstProps({ ...instProps, [name]: e.target.value })} className="w-full border rounded px-2 py-1 text-xs"><option value="">—</option><option value="true">是</option><option value="false">否</option></select>
                        ) : def.type === 'number' ? (
                          <input type="number" value={instProps[name] || ''} onChange={e => setInstProps({ ...instProps, [name]: e.target.value })} className="w-full border rounded px-2 py-1 text-xs" />
                        ) : (
                          <input value={instProps[name] || ''} onChange={e => setInstProps({ ...instProps, [name]: e.target.value })} className="w-full border rounded px-2 py-1 text-xs" />
                        )}
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex gap-2 justify-end">
                  {isEdit ? (
                    <button onClick={() => updateInstMut.mutate({ id: editInstId!, data: { name_cn: instForm.name_cn, name_en: instForm.name_en, description: instForm.description, properties: buildProps() } })} disabled={!instForm.name_cn}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 更新</button>
                  ) : (
                    <button onClick={() => createInstMut.mutate({ name_cn: instForm.name_cn, name_en: instForm.name_en, description: instForm.description, object_type_id: showInstForm, properties: buildProps() })} disabled={!instForm.name_cn}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 创建</button>
                  )}
                  <button onClick={close} className="px-4 py-2 border rounded-lg text-sm text-gray-500">取消</button>
                </div>
              </div>
            </div>
          </div>
        )
      })()}

      {/* ── 编辑/新增弹窗 ── */}
      {(showNew || editId || newChildParentId) && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={()=>{setShowNew(false);setEditId(null);setNewChildParentId(null)}}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-xl max-h-[75vh] overflow-auto m-4" onClick={e=>e.stopPropagation()}>
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between"><h3 className="font-semibold text-gray-800">{editingTitle}</h3><button onClick={()=>{setShowNew(false);setEditId(null);setNewChildParentId(null)}} className="text-gray-400 hover:text-gray-600"><X size={18}/></button></div>
              <input value={form.name_cn} onChange={e=>setForm({...form,name_cn:e.target.value})} placeholder="中文名 *" className="w-full border rounded-lg px-3 py-2 text-sm"/>
              <input value={form.name_en} onChange={e=>setForm({...form,name_en:e.target.value})} placeholder="英文名" className="w-full border rounded-lg px-3 py-2 text-sm"/>
              <input value={form.description} onChange={e=>setForm({...form,description:e.target.value})} placeholder="描述" className="w-full border rounded-lg px-3 py-2 text-sm"/>
              <div className="border-t pt-3 space-y-2">
                <div className="flex items-center justify-between"><p className="text-xs font-medium text-gray-500">属性字段定义</p><button onClick={addField} className="text-xs text-blue-600 hover:text-blue-800">+ 添加字段</button></div>
                {fields.map(f=>(
                  <div key={f.key} className="flex items-center gap-2">
                    <input value={f.name} onChange={e=>updateField(f.key,{name:e.target.value})} placeholder="字段名" className="flex-1 border rounded px-2 py-1 text-xs"/>
                    <select value={f.type} onChange={e=>updateField(f.key,{type:e.target.value})} className="border rounded px-2 py-1 text-xs w-18"><option value="string">文本</option><option value="number">数字</option><option value="boolean">布尔</option></select>
                    <input value={f.unit} onChange={e=>updateField(f.key,{unit:e.target.value})} placeholder="单位" className="border rounded px-2 py-1 text-xs w-14"/>
                    <button onClick={()=>removeField(f.key)} className="text-gray-300 hover:text-red-500"><Trash2 size={10}/></button>
                  </div>
                ))}
              </div>
              {error && <p className="text-red-500 text-xs bg-red-50 p-2 rounded">{error}</p>}
              <div className="flex gap-2 justify-end">
                {editId
                  ? <button onClick={()=>updateMut.mutate({id:editId,data:{name_cn:form.name_cn,name_en:form.name_en,description:form.description,property_schema:buildSchema()}})} disabled={!form.name_cn} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14}/> 更新</button>
                  : <button onClick={()=>{const d:any={name_cn:form.name_cn,name_en:form.name_en,description:form.description,property_schema:buildSchema()};if(newChildParentId)d.parent_id=newChildParentId;createMut.mutate(d)}} disabled={!form.name_cn} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14}/> 创建</button>
                }
                <button onClick={()=>{setShowNew(false);setEditId(null);setNewChildParentId(null)}} className="px-4 py-2 border rounded-lg text-sm text-gray-500">取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
      {/* ── 规则编辑器弹窗 ── */}
      {showRuleEditor && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setShowRuleEditor(null)}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-auto m-4" onClick={e => e.stopPropagation()}>
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between"><h3 className="font-semibold text-gray-800">{showRuleEditor.editId ? '编辑规则' : '新增规则'} — {showRuleEditor.targetType==='type'?'本体层':'实体层'}</h3><button onClick={() => setShowRuleEditor(null)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button></div>
              <p className="text-xs text-gray-400">{showRuleEditor.targetType==='type'?'此规则适用于该本体下的所有实体':'此规则仅适用于该实体'}</p>
              <input value={ruleForm.name_cn} onChange={e => setRuleForm({ ...ruleForm, name_cn: e.target.value })} placeholder="规则名称 *" className="w-full border rounded-lg px-3 py-2 text-sm" />
              <input value={ruleForm.description} onChange={e => setRuleForm({ ...ruleForm, description: e.target.value })} placeholder="描述（可选）" className="w-full border rounded-lg px-3 py-2 text-sm" />
              <div className="relative">
                <textarea value={ruleForm.python_code} onChange={e => setRuleForm({ ...ruleForm, python_code: e.target.value })} rows={12} spellCheck={false}
                  className="w-full border rounded-lg px-3 py-3 text-sm font-mono bg-gray-900 text-green-400 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-y" />
                <button onClick={() => { try { Function(`"use strict"; return (${ruleForm.python_code})`)(); alert('语法检查通过 ✓') } catch (e: any) { alert('语法错误：' + e.message) } }}
                  className="absolute top-2 right-2 flex items-center gap-1 text-[10px] bg-gray-700 text-gray-300 hover:text-white px-2 py-1 rounded"><Play size={10} /> 测试语法</button>
              </div>
              <div className="flex gap-2 justify-end">
                {showRuleEditor.editId ? (
                  <button onClick={() => updateRuleMut.mutate({ id: showRuleEditor.editId!, data: ruleForm })} disabled={!ruleForm.name_cn}
                    className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 更新</button>
                ) : (
                  <button onClick={() => createRuleMut.mutate({ ...ruleForm, object_type_id: showRuleEditor.targetType==='type'?showRuleEditor.targetId:undefined, object_instance_id: showRuleEditor.targetType==='instance'?showRuleEditor.targetId:undefined })} disabled={!ruleForm.name_cn}
                    className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 创建</button>
                )}
                <button onClick={() => setShowRuleEditor(null)} className="px-4 py-2 border rounded-lg text-sm text-gray-500">取消</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── 动作编辑器弹窗 ── */}
      {showActionEditor && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setShowActionEditor(null)}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-auto m-4" onClick={e => e.stopPropagation()}>
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between"><h3 className="font-semibold text-gray-800">{showActionEditor.editId ? '编辑动作' : '新增动作'} — {showActionEditor.targetType==='type'?'本体层':'实体层'}</h3><button onClick={() => setShowActionEditor(null)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button></div>
              <p className="text-xs text-gray-400">{showActionEditor.targetType==='type'?'此动作适用于该本体下的所有实体':'此动作仅适用于该实体'}</p>
              <input value={actionForm.name_cn} onChange={e => setActionForm({ ...actionForm, name_cn: e.target.value })} placeholder="动作名称 *" className="w-full border rounded-lg px-3 py-2 text-sm" />
              <input value={actionForm.description} onChange={e => setActionForm({ ...actionForm, description: e.target.value })} placeholder="描述（可选）" className="w-full border rounded-lg px-3 py-2 text-sm" />
              <div className="relative">
                <textarea value={actionForm.python_code} onChange={e => setActionForm({ ...actionForm, python_code: e.target.value })} rows={12} spellCheck={false}
                  className="w-full border rounded-lg px-3 py-3 text-sm font-mono bg-gray-900 text-green-400 focus:outline-none focus:ring-2 focus:ring-amber-500 resize-y" />
                <button onClick={() => { try { Function(`"use strict"; return (${actionForm.python_code})`)(); alert('语法检查通过 ✓') } catch (e: any) { alert('语法错误：' + e.message) } }}
                  className="absolute top-2 right-2 flex items-center gap-1 text-[10px] bg-gray-700 text-gray-300 hover:text-white px-2 py-1 rounded"><Play size={10} /> 测试语法</button>
              </div>
              <div className="flex gap-2 justify-end">
                {showActionEditor.editId ? (
                  <button onClick={() => updateActionMut.mutate({ id: showActionEditor.editId!, data: actionForm })} disabled={!actionForm.name_cn}
                    className="px-4 py-2 bg-amber-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 更新</button>
                ) : (
                  <button onClick={() => createActionMut.mutate({ ...actionForm, object_type_id: showActionEditor.targetType==='type'?showActionEditor.targetId:undefined, object_instance_id: showActionEditor.targetType==='instance'?showActionEditor.targetId:undefined })} disabled={!actionForm.name_cn}
                    className="px-4 py-2 bg-amber-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 创建</button>
                )}
                <button onClick={() => setShowActionEditor(null)} className="px-4 py-2 border rounded-lg text-sm text-gray-500">取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
      {/* ── 关系类型编辑弹窗 ── */}
      {showLinkForm && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => { setShowLinkForm(false); setEditLinkId(null) }}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md m-4" onClick={e => e.stopPropagation()}>
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between"><h3 className="font-semibold text-gray-800">{editLinkId ? '编辑关系类型' : '新增关系类型'}</h3><button onClick={() => { setShowLinkForm(false); setEditLinkId(null) }} className="text-gray-400 hover:text-gray-600"><X size={18} /></button></div>
              <input value={linkForm.name_cn} onChange={e => setLinkForm({ ...linkForm, name_cn: e.target.value })} placeholder="中文名 (如: 探测流)" className="w-full border rounded-lg px-3 py-2 text-sm" />
              <input value={linkForm.name_en} onChange={e => setLinkForm({ ...linkForm, name_en: e.target.value })} placeholder="英文名 (如: DETECT_FLOW)" className="w-full border rounded-lg px-3 py-2 text-sm font-mono" />
              <input value={linkForm.description} onChange={e => setLinkForm({ ...linkForm, description: e.target.value })} placeholder="描述" className="w-full border rounded-lg px-3 py-2 text-sm" />
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">源类型（从哪来）</label>
                  <select value={linkForm.source_object_type_id} onChange={e => setLinkForm({ ...linkForm, source_object_type_id: e.target.value })}
                    className="w-full border rounded-lg px-3 py-2 text-sm">
                    <option value="">不限</option>
                    {(types as ObjectType[]).map(t => <option key={t.id} value={t.id}>{t.name_cn}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">目标类型（指向谁）</label>
                  <select value={linkForm.target_object_type_id} onChange={e => setLinkForm({ ...linkForm, target_object_type_id: e.target.value })}
                    className="w-full border rounded-lg px-3 py-2 text-sm">
                    <option value="">不限</option>
                    {(types as ObjectType[]).map(t => <option key={t.id} value={t.id}>{t.name_cn}</option>)}
                  </select>
                </div>
              </div>
              <div className="border-t pt-3 space-y-2">
                <div className="flex items-center justify-between"><p className="text-xs font-medium text-gray-500">边属性定义</p>
                  <button onClick={() => setLinkFields(p => [...p, { key: `lf-${Date.now()}`, name: '', type: 'string', unit: '' }])} className="text-xs text-green-600 hover:text-green-800">+ 添加字段</button>
                </div>
                {linkFields.map(f => (
                  <div key={f.key} className="flex items-center gap-2">
                    <input value={f.name} onChange={e => setLinkFields(p => p.map(x => x.key === f.key ? { ...x, name: e.target.value } : x))} placeholder="字段名" className="flex-1 border rounded px-2 py-1 text-xs" />
                    <select value={f.type} onChange={e => setLinkFields(p => p.map(x => x.key === f.key ? { ...x, type: e.target.value } : x))} className="border rounded px-2 py-1 text-xs w-18"><option value="string">文本</option><option value="number">数字</option><option value="boolean">布尔</option></select>
                    <input value={f.unit} onChange={e => setLinkFields(p => p.map(x => x.key === f.key ? { ...x, unit: e.target.value } : x))} placeholder="单位" className="border rounded px-2 py-1 text-xs w-14" />
                    <button onClick={() => setLinkFields(p => p.filter(x => x.key !== f.key))} className="text-gray-300 hover:text-red-500"><Trash2 size={10} /></button>
                  </div>
                ))}
              </div>
              <div className="flex gap-2 justify-end">
                {editLinkId ? (
                  <button onClick={() => { const ps:Record<string,any>={};linkFields.forEach(f=>{if(f.name.trim())ps[f.name.trim()]={type:f.type,unit:f.unit||undefined}});updateLinkMut.mutate({id:editLinkId,data:{...linkForm,property_schema:ps}}) }} className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm"><Save size={14} /> 更新</button>
                ) : (
                  <button onClick={() => { const ps:Record<string,any>={};linkFields.forEach(f=>{if(f.name.trim())ps[f.name.trim()]={type:f.type,unit:f.unit||undefined}});createLinkMut.mutate({...linkForm,property_schema:ps}) }} disabled={!linkForm.name_cn && !linkForm.name_en} className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm disabled:opacity-40"><Save size={14} /> 创建</button>
                )}
                <button onClick={() => { setShowLinkForm(false); setEditLinkId(null) }} className="px-4 py-2 border rounded-lg text-sm text-gray-500">取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
