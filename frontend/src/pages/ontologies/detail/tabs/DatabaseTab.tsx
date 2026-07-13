import { useState, useEffect } from 'react'
import { Plus, Loader2, Database, Table2, Columns3, Check, X, Eye, Bookmark } from 'lucide-react'
import { apiClientV2 } from '@/api/client'
import { ontologyApi } from '@/api/ontologies'

interface ColumnInfo { name: string; type: string }

export default function DatabaseTab({ ontologyId }: { ontologyId: string }) {
  const [conn, setConn] = useState({ db_type: 'mysql', host: '', port: 3306, user: '', password: '', database: '' })
  const [connected, setConnected] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testMsg, setTestMsg] = useState('')
  const [tables, setTables] = useState<string[]>([])
  const [columns, setColumns] = useState<ColumnInfo[]>([])
  const [preview, setPreview] = useState<any>(null)
  const [selectedTable, setSelectedTable] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedCols, setSelectedCols] = useState<Set<string>>(new Set())
  const [savedSources, setSavedSources] = useState<any[]>([])

  useEffect(() => {
    ontologyApi.listDataSources(ontologyId).then((r: any) => {
      setSavedSources(Array.isArray(r) ? r : (r?.data || []))
    }).catch(() => {})
  }, [ontologyId])

  async function testConn() {
    setTesting(true); setTestMsg('')
    try {
      const res: any = await apiClientV2.post('/db/test-connection', conn)
      setTestMsg(res.message || JSON.stringify(res))
      setConnected(res.ok)
    } catch (e: any) { setTestMsg('连接失败: ' + String(e)) }
    finally { setTesting(false) }
  }

  async function fetchTables() {
    setLoading(true)
    try {
      const res: any = await apiClientV2.post('/db/tables', conn)
      setTables(res.tables || [])
    } catch (e: any) { alert(String(e)) }
    finally { setLoading(false) }
  }

  async function fetchColumns(table: string) {
    setSelectedTable(table); setLoading(true); setColumns([]); setPreview(null); setSelectedCols(new Set())
    try {
      const [colRes, prevRes]: any[] = await Promise.all([
        apiClientV2.post('/db/columns', conn, { params: { table_name: table } }),
        apiClientV2.post('/db/preview', conn, { params: { table_name: table, limit: 5 } }),
      ])
      setColumns(colRes.columns || [])
      setPreview(prevRes)
    } catch (e: any) { alert(String(e)) }
    finally { setLoading(false) }
  }

  async function importAsProperties() {
    if (selectedCols.size === 0) { alert('请至少选择一列'); return }
    const schema: Record<string, { type: string }> = {}
    selectedCols.forEach(name => {
      const col = columns.find(c => c.name === name)
      const mappedType = col?.type?.toLowerCase().includes('int') || col?.type?.toLowerCase().includes('float') || col?.type?.toLowerCase().includes('double') || col?.type?.toLowerCase().includes('decimal') || col?.type?.toLowerCase().includes('numeric') ? 'number'
        : col?.type?.toLowerCase().includes('bool') ? 'boolean' : 'string'
      schema[name] = { type: mappedType }
    })
    const name = selectedTable || 'imported_type'
    try {
      await apiClientV2.post(`/ontologies/${ontologyId}/object-types`, {
        name_cn: name, name_en: name,
        description: `从数据库表 ${selectedTable} 导入`,
        property_schema: schema,
      })
      alert(`已创建本体类型: ${name}，包含 ${Object.keys(schema).length} 个字段`)
    } catch (e: any) { alert('创建失败: ' + String(e)) }
  }

  async function importAllRows(ontologyId: string, objectTypeId: string, tableName: string) {
    if (!confirm(`将表 ${tableName} 的所有行导入为 ${selectedTable} 的实体实例？`)) return
    setLoading(true)
    try {
      // 获取全部数据
      const data: any = await apiClientV2.post('/db/preview', conn, { params: { table_name: tableName, limit: 1000 } })
      const existingTypes: any = await apiClientV2.get(`/ontologies/${ontologyId}/object-types`)
      const types = existingTypes?.data || existingTypes || []
      const targetType = types.find((t: any) => t.name_cn === selectedTable || t.id === objectTypeId)
      if (!targetType) { alert('请先点击"导入为本体"创建类型'); return }

      let created = 0
      for (const row of data.rows || []) {
        const nameCol = data.columns?.[0] || 'id'
        const instanceName = row[nameCol] || `row_${created}`
        await apiClientV2.post(`/ontologies/${ontologyId}/object-instances`, {
          name_cn: String(instanceName),
          object_type_id: targetType.id,
          properties: row,
        })
        created++
      }
      alert(`已导入 ${created} 个实体实例`)
    } catch (e: any) { alert('导入失败: ' + String(e)) }
    finally { setLoading(false) }
  }

  return (
    <div className="space-y-6">
      <h3 className="font-semibold text-sm text-gray-800">远程数据库连接</h3>

      {/* Saved Sources */}
      {savedSources.length > 0 && (
        <div className="bg-white border rounded-xl p-4">
          <h4 className="text-xs font-medium text-gray-500 mb-2 flex items-center gap-1"><Bookmark size={12} /> 已保存的数据源</h4>
          <div className="flex flex-wrap gap-2">
            {savedSources.map((s: any) => (
              <button key={s.id} onClick={() => {
                const cfg = s.db_config || {}
                setConn({ ...conn, ...cfg })
                setSelectedTable(s.registered_table || '')
              }}
                className="px-3 py-1.5 border rounded-lg text-xs hover:bg-gray-50 flex items-center gap-2 group">
                <Database size={12} className="text-green-500" />
                <span>{s.name}</span>
                <span className="text-gray-400">{s.registered_table}</span>
                <X size={10} className="text-gray-300 hover:text-red-500 hidden group-hover:inline"
                  onClick={(e) => { e.stopPropagation(); ontologyApi.deleteDataSource(ontologyId, s.id).then(() => setSavedSources(prev => prev.filter(x => x.id !== s.id))) }} />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Connection Form */}
      <div className="bg-white border rounded-xl p-5 space-y-3">
        <div className="grid grid-cols-4 gap-3">
          <div>
            <label className="block text-[10px] text-gray-500 mb-0.5">类型</label>
            <select value={conn.db_type} onChange={e => setConn({ ...conn, db_type: e.target.value, port: e.target.value === 'postgres' ? 5432 : 3306 })}
              className="w-full border rounded px-2 py-1.5 text-xs">
              <option value="mysql">MySQL</option>
              <option value="postgres">PostgreSQL</option>
            </select>
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 mb-0.5">主机</label>
            <input value={conn.host} onChange={e => setConn({ ...conn, host: e.target.value })} placeholder="localhost" className="w-full border rounded px-2 py-1.5 text-xs" />
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 mb-0.5">端口</label>
            <input type="number" value={conn.port} onChange={e => setConn({ ...conn, port: +e.target.value })} className="w-full border rounded px-2 py-1.5 text-xs" />
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 mb-0.5">数据库名</label>
            <input value={conn.database} onChange={e => setConn({ ...conn, database: e.target.value })} placeholder="mydb" className="w-full border rounded px-2 py-1.5 text-xs" />
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 mb-0.5">用户名</label>
            <input value={conn.user} onChange={e => setConn({ ...conn, user: e.target.value })} placeholder="root" className="w-full border rounded px-2 py-1.5 text-xs" />
          </div>
          <div>
            <label className="block text-[10px] text-gray-500 mb-0.5">密码</label>
            <input type="password" value={conn.password} onChange={e => setConn({ ...conn, password: e.target.value })} className="w-full border rounded px-2 py-1.5 text-xs" />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={testConn} disabled={testing || !conn.host || !conn.database}
            className="px-3 py-1.5 bg-black text-white rounded-lg text-xs flex items-center gap-1 disabled:opacity-40">
            {testing && <Loader2 size={12} className="animate-spin" />} 测试连接
          </button>
          {testMsg && <span className={`text-xs ${connected ? 'text-green-600' : 'text-red-500'}`}>{testMsg}</span>}
          {connected && (
            <>
              <button onClick={fetchTables} className="px-3 py-1.5 border rounded-lg text-xs text-gray-600 hover:bg-gray-50 flex items-center gap-1">
                <Database size={12} /> 浏览表
              </button>
              {selectedTable && (
                <button onClick={async () => {
                  try {
                    await apiClientV2.post(`/ontologies/${ontologyId}/data-sources`, {
                      name: `${conn.database}.${selectedTable}`,
                      db_config: conn,
                      registered_table: selectedTable,
                    })
                    alert(`已保存数据源: ${conn.database}.${selectedTable}`)
                  } catch (e: any) { alert('保存失败: ' + String(e)) }
                }} className="px-3 py-1.5 bg-green-600 text-white rounded-lg text-xs flex items-center gap-1">
                  <Plus size={12} /> 保存数据源
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Table List + Columns */}
      {tables.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Tables */}
          <div className="bg-white border rounded-xl overflow-hidden">
            <div className="px-4 py-2.5 border-b bg-gray-50"><span className="text-xs font-medium text-gray-600">表 ({tables.length})</span></div>
            <div className="max-h-80 overflow-auto">
              {tables.map(t => (
                <button key={t} onClick={() => fetchColumns(t)}
                  className={`w-full text-left px-4 py-2 text-xs border-t hover:bg-gray-50 flex items-center gap-2 ${
                    selectedTable === t ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-700'}`}>
                  <Table2 size={12} /> {t}
                </button>
              ))}
            </div>
          </div>

          {/* Columns */}
          <div className="bg-white border rounded-xl overflow-hidden">
            <div className="px-4 py-2.5 border-b bg-gray-50 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-600">列 ({columns.length})</span>
              {columns.length > 0 && (
                <div className="flex items-center gap-2">
                  <button onClick={importAsProperties} className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1">
                    <Plus size={10} /> 导入为本体
                  </button>
                  <button onClick={() => importAllRows(ontologyId, '', selectedTable)} disabled={loading}
                    className="text-xs text-green-600 hover:text-green-800 flex items-center gap-1">
                    <Plus size={10} /> 导入所有行为实体
                  </button>
                </div>
              )}
            </div>
            <div className="max-h-80 overflow-auto">
              {loading && <div className="px-4 py-3 text-xs text-gray-400">加载中...</div>}
              {columns.map(c => (
                <label key={c.name} className={`flex items-center gap-2 px-4 py-1.5 text-xs border-t cursor-pointer hover:bg-gray-50 ${
                  selectedCols.has(c.name) ? 'bg-blue-50' : ''}`}>
                  <input type="checkbox" checked={selectedCols.has(c.name)}
                    onChange={() => { const s = new Set(selectedCols); s.has(c.name) ? s.delete(c.name) : s.add(c.name); setSelectedCols(s) }}
                    className="rounded" />
                  <Columns3 size={12} className="text-gray-400" />
                  <span>{c.name}</span>
                  <span className="text-gray-400 ml-auto">{c.type}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Preview */}
          <div className="bg-white border rounded-xl overflow-hidden">
            <div className="px-4 py-2.5 border-b bg-gray-50"><span className="text-xs font-medium text-gray-600">数据预览</span></div>
            {preview ? (
              <div className="overflow-auto max-h-80">
                <table className="w-full text-[10px]">
                  <thead>
                    <tr className="bg-gray-50">
                      {preview.columns?.map((c: string) => <th key={c} className="px-2 py-1 text-left text-gray-500 font-medium">{c}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows?.map((row: any, i: number) => (
                      <tr key={i} className="border-t">
                        {preview.columns?.map((c: string) => <td key={c} className="px-2 py-1 text-gray-700">{row[c]}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="px-4 py-8 text-center text-xs text-gray-400"><Eye size={20} className="mx-auto mb-1 text-gray-300" />选择表查看数据</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
