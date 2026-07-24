import { useEffect, useMemo, useRef, Component, type ReactNode } from 'react'
import { MapContainer, TileLayer, Marker, Polyline, Tooltip, Circle, useMap } from 'react-leaflet'
import L from 'leaflet'

class MapErrorBoundary extends Component<{ children: ReactNode; fallback?: ReactNode }, { hasError: boolean }> {
  constructor(props: any) { super(props); this.state = { hasError: false } }
  static getDerivedStateFromError() { return { hasError: true } }
  render() {
    if (this.state.hasError) return this.props.fallback || <div className="flex items-center justify-center h-full bg-gray-50 text-gray-400 text-sm">地图加载失败</div>
    return this.props.children
  }
}

// Fix Leaflet default icon issue with bundlers
import iconUrl from 'leaflet/dist/images/marker-icon.png'
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png'
import shadowUrl from 'leaflet/dist/images/marker-shadow.png'

delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({ iconUrl, iconRetinaUrl, shadowUrl })

// 用简洁的色点 + 标签代替 emoji
const ENTITY_COLORS: Record<string, { fill: string; stroke: string }> = {
  missile:     { fill: '#ef4444', stroke: '#991b1b' },
  radar:       { fill: '#3b82f6', stroke: '#1e40af' },
  interceptor: { fill: '#22c55e', stroke: '#166534' },
  default:     { fill: '#6b7280', stroke: '#374151' },
}

function getTypeStyle(name: string) {
  if (name.includes('导弹') || name.includes('26B')) return ENTITY_COLORS.missile
  if (name.includes('雷达')) return ENTITY_COLORS.radar
  if (name.includes('红旗') || name.includes('拦截')) return ENTITY_COLORS.interceptor
  return ENTITY_COLORS.default
}

function makeIcon(name: string) {
  const c = getTypeStyle(name)
  return L.divIcon({
    html: `<div style="width:16px;height:16px;border-radius:50%;background:${c.fill};border:3px solid white;box-shadow:0 0 10px ${c.fill}cc, 0 2px 6px rgba(0,0,0,0.3)"></div>`,
    className: '', iconSize: [16, 16], iconAnchor: [8, 8],
  })
}

const LINK_COLORS: Record<string, { color: string; dash: string }> = {
  detect: { color: '#3b82f6', dash: '10,6' },
  Detect: { color: '#3b82f6', dash: '10,6' },
  intercept: { color: '#dc2626', dash: '' },
  Intercept: { color: '#dc2626', dash: '' },
}

// 计算平行偏移 — 多发方案画多条平行线区分
function parallelOffset(lat1: number, lon1: number, lat2: number, lon2: number, offsetDeg: number): [number, number] {
  const dlat = lat2 - lat1, dlon = lon2 - lon1
  const len = Math.sqrt(dlat * dlat + dlon * dlon) || 1
  // 垂直方向 (归一化 × 偏移量)
  return [-dlon / len * offsetDeg, dlat / len * offsetDeg]
}

// Auto-fit map bounds
function FitBounds({ positions }: { positions: [number, number][] }) {
  const map = useMap()
  const prevRef = useRef<string>('')
  const key = JSON.stringify(positions)
  useEffect(() => {
    if (positions.length > 0 && key !== prevRef.current) {
      prevRef.current = key
      const bounds = L.latLngBounds(positions)
      if (bounds.isValid()) map.fitBounds(bounds.pad(0.3), { animate: true, duration: 0.8 })
    }
  }, [key, map, positions])
  return null
}

export interface MapEntity {
  id: string
  name: string
  lat: number
  lon: number
  type?: string
}

export interface MapLink {
  id?: string
  sourceName: string
  targetName: string
  sourceLat: number
  sourceLon: number
  targetLat: number
  targetLon: number
  linkTypeId?: string
  count?: number  // 弹药数量，用于多发方案显示多条平行线
}

export default function SimulationMap({
  entities,
  links,
  trail,
  height = '100%',
}: {
  entities: MapEntity[]
  links: MapLink[]
  trail?: [number, number][]
  height?: string
}) {
  const positions = useMemo(() => entities.map(e => [e.lat, e.lon] as [number, number]), [entities])

  // Classify links by type
  const detectLinks = useMemo(() => links.filter(l => {
    const t = (l.linkTypeId || '').toLowerCase()
    return t.includes('detect') || t.includes('探测')
  }), [links])
  const interceptLinks = useMemo(() => links.filter(l => {
    const t = (l.linkTypeId || '').toLowerCase()
    return t.includes('intercept') || t.includes('拦截') || t.includes('fire') || t.includes('火力')
  }), [links])
  const threatLinks = useMemo(() => links.filter(l => {
    const t = (l.linkTypeId || '').toLowerCase()
    return t.includes('threat') || t.includes('威胁')
  }), [links])
  const otherLinks = useMemo(() => links.filter(l => {
    const t = (l.linkTypeId || '').toLowerCase()
    return !t.includes('detect') && !t.includes('探测') && !t.includes('intercept') && !t.includes('拦截') && !t.includes('fire') && !t.includes('火力') && !t.includes('threat') && !t.includes('威胁')
  }), [links])

  return (
    <div style={{ height, width: '100%', borderRadius: 8, overflow: 'hidden' }}>
      <MapErrorBoundary>
      <MapContainer
        center={[29, 120]}
        zoom={6}
        style={{ height: '100%', width: '100%' }}
        attributionControl={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        />

        {/* Trail */}
        {trail && trail.length > 1 && (
          <Polyline positions={trail} color="#9ca3af" weight={1.5} dashArray="4,4" />
        )}

        {/* Detection links - 亮蓝色粗线 */}
        {detectLinks.map((l, i) => (
          <Polyline
            key={`detect-${i}`}
            positions={[[l.sourceLat, l.sourceLon], [l.targetLat, l.targetLon]]}
            color="#3b82f6" weight={4} dashArray="10,6" opacity={0.9}
          >
            <Tooltip sticky>{l.sourceName} 探测 {l.targetName}</Tooltip>
          </Polyline>
        ))}

        {/* Interception links - 鲜红色粗线，多发方案画多条平行线 */}
        {interceptLinks.flatMap((l, i) => {
          const count = l.count || 1
          const offsetDeg = 0.008 // ~900m 平行间距
          // 计算每条平行线的偏移量
          const lines: JSX.Element[] = []
          for (let j = 0; j < count; j++) {
            const shift = (j - (count - 1) / 2) * offsetDeg // 居中分布
            const [pdlat, pdlon] = parallelOffset(l.sourceLat, l.sourceLon, l.targetLat, l.targetLon, shift)
            lines.push(
              <Polyline
                key={`intercept-${i}-${j}`}
                positions={[[l.sourceLat + pdlat, l.sourceLon + pdlon], [l.targetLat + pdlat, l.targetLon + pdlon]]}
                color="#ef4444" weight={count > 1 ? 3 : 4} opacity={1}
              >
                {j === 0 && (
                  <Tooltip sticky>{l.sourceName} 拦截 {l.targetName} {count > 1 ? `×${count}发` : ''}</Tooltip>
                )}
              </Polyline>
            )
          }
          return lines
        })}

        {/* Threat links - 橙色威胁线 */}
        {threatLinks.map((l, i) => (
          <Polyline
            key={`threat-${i}`}
            positions={[[l.sourceLat, l.sourceLon], [l.targetLat, l.targetLon]]}
            color="#f97316" weight={3} dashArray="8,4" opacity={0.85}
          >
            <Tooltip sticky>{l.sourceName} 威胁 {l.targetName}</Tooltip>
          </Polyline>
        ))}

        {/* Other links */}
        {otherLinks.map((l, i) => (
          <Polyline
            key={`other-${i}`}
            positions={[[l.sourceLat, l.sourceLon], [l.targetLat, l.targetLon]]}
            color="#6b7280" weight={1.5} dashArray="4,4"
          />
        ))}

        {/* Entity markers */}
        {entities.map(e => (
          <Marker key={e.id} position={[e.lat, e.lon]} icon={makeIcon(e.name)}>
            <Tooltip permanent direction="right" offset={[8, 0]} className="!bg-transparent !border-0 !shadow-none !text-[11px] !font-medium !p-0">
              <span style={{ color: getTypeStyle(e.name).fill, textShadow: '0 0 4px white, 0 0 4px white' }}>{e.name}</span>
            </Tooltip>
          </Marker>
        ))}

        {/* Detection range circles */}
        {entities.filter(e => e.name.includes('雷达')).map(e => {
          const rangeKm = 500
          return (
            <Circle
              key={`range-${e.id}`}
              center={[e.lat, e.lon]}
              radius={rangeKm * 1000}
              pathOptions={{ color: '#3b82f6', fillColor: '#3b82f6', fillOpacity: 0.03, weight: 1, dashArray: '4,4' }}
            />
          )
        })}

        <FitBounds positions={positions} />
      </MapContainer>
      </MapErrorBoundary>
    </div>
  )
}
