import { useEffect, useRef } from 'react'
import cytoscape from 'cytoscape'
import type { MapEntity, MapLink } from './SimulationMap'

const TYPE_COLORS: Record<string, string> = {
  missile: '#ef4444', radar: '#3b82f6', interceptor: '#22c55e',
  弹道导弹: '#ef4444', 雷达站: '#3b82f6', 拦截弹: '#22c55e',
}

function getColor(name: string): string {
  if (name.includes('导弹') || name.includes('26B')) return TYPE_COLORS.missile
  if (name.includes('雷达')) return TYPE_COLORS.radar
  if (name.includes('红旗') || name.includes('拦截')) return TYPE_COLORS.interceptor
  return '#6b7280'
}

export default function ScenarioGraph({
  entities, links, height = 240,
}: {
  entities: MapEntity[]
  links: MapLink[]
  height?: number
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const cyNodes = entities.map(e => ({
      data: {
        id: e.id,
        label: e.name.length > 6 ? e.name.slice(0, 6) + '…' : e.name,
        color: getColor(e.name),
      }
    }))

    const edgeSet = new Set<string>()
    const cyEdges = links.filter(l => {
      const key = `${l.sourceName}|${l.targetName}|${l.linkTypeId}`
      if (edgeSet.has(key)) return false
      edgeSet.add(key)
      return true
    }).map(l => {
      const srcEnt = entities.find(e => e.name === l.sourceName)
      const tgtEnt = entities.find(e => e.name === l.targetName)
      return {
        data: {
          id: `${srcEnt?.id || l.sourceName}-${tgtEnt?.id || l.targetName}-${l.linkTypeId}`,
          source: srcEnt?.id || l.sourceName,
          target: tgtEnt?.id || l.targetName,
          label: (l.linkTypeId || '').includes('detect') || (l.linkTypeId || '').includes('探测')
            ? '探测' : (l.linkTypeId || '').includes('intercept') || (l.linkTypeId || '').includes('拦截')
            ? '拦截' : (l.linkTypeId || '').slice(0, 4),
          edgeColor: (l.linkTypeId || '').includes('intercept') || (l.linkTypeId || '').includes('拦截')
            ? '#ef4444' : '#3b82f6',
        }
      }
    })

    cyRef.current?.destroy()

    const cy = cytoscape({
      container: containerRef.current,
      elements: [...cyNodes, ...cyEdges],
      layout: {
        name: 'cose',
        animate: false,
        fit: true,
        padding: 20,
        nodeRepulsion: () => 6000,
        idealEdgeLength: () => 100,
        gravity: 0.3,
        numIter: 400,
      } as any,
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'background-color': 'data(color)',
            color: '#fff',
            'font-size': '9px',
            'font-weight': 'bold',
            'text-valign': 'center',
            'text-halign': 'center',
            width: 40,
            height: 40,
            'text-outline-width': 1.5,
            'text-outline-color': 'data(color)',
          }
        },
        {
          selector: 'edge',
          style: {
            label: 'data(label)',
            'font-size': '8px',
            color: '#374151',
            'line-color': 'data(edgeColor)',
            'target-arrow-color': 'data(edgeColor)',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'text-background-color': '#ffffff',
            'text-background-opacity': 0.9,
            'text-background-padding': '1px',
            width: 1.5,
          }
        },
      ],
    })

    cyRef.current = cy

    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [entities, links])

  return (
    <div className="border rounded-lg overflow-hidden bg-white flex flex-col" style={{ height }}>
      <div className="flex items-center gap-1 px-2 py-1 border-b bg-gray-50 flex-shrink-0">
        <span className="text-[10px] font-semibold text-gray-500">场景图谱</span>
        <span className="text-[10px] text-gray-400 ml-auto">{entities.length}节点 {links.length}边</span>
      </div>
      <div ref={containerRef} className="flex-1" />
    </div>
  )
}
