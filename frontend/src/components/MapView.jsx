import { useMemo } from 'react'
import { MapContainer, TileLayer, CircleMarker, Polyline, Marker, Tooltip, Popup } from 'react-leaflet'
import L from 'leaflet'
import { RES, RESOURCES, urgencyColor, fmt } from '../api.js'

const depotIcon = L.divIcon({ className: '', html: '<div style="width:18px;height:18px;background:#4cc2ff;border:2px solid #fff;transform:rotate(45deg);box-shadow:0 0 6px #4cc2ff"></div>', iconSize: [18, 18], iconAnchor: [9, 9] })
const junctionIcon = L.divIcon({ className: '', html: '<div style="width:8px;height:8px;background:#8b98a5;border-radius:50%;border:1px solid #fff"></div>', iconSize: [8, 8], iconAnchor: [4, 4] })

export default function MapView({ scenario, plan, selected, onSelectZone }) {
  const nodes = useMemo(() => {
    if (!scenario) return {}
    const n = { [scenario.depot.id]: scenario.depot.coordinates }
    scenario.junctions.forEach((j) => { n[j.id] = j.coordinates })
    scenario.zones.forEach((z) => { n[z.id] = z.coordinates })
    return n
  }, [scenario])

  const closedEdges = useMemo(() => {
    if (!scenario) return []
    const key = (e) => [e.a, e.b].sort().join('|')
    const open = new Set(scenario.edges.map(key))
    return scenario.base_edges.filter((e) => !open.has(key(e)))
  }, [scenario])

  if (!scenario) return <div className="map panel">Loading map…</div>

  const zoneInfo = Object.fromEntries((plan?.zones || scenario.zone_summaries).map((z) => [z.id, z]))
  const unitsByZone = {}
  ;(plan?.allocations || []).forEach((a) => {
    if (a.units > 0) (unitsByZone[a.zone] ||= {})[a.resource] = a
  })

  return (
    <div>
      <MapContainer center={[9.78, 76.45]} zoom={9} className="map" scrollWheelZoom={false}>
        <TileLayer attribution='&copy; OpenStreetMap contributors' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" className="tiles-dark" />

        {scenario.edges.map((e, i) => nodes[e.a] && nodes[e.b] && (
          <Polyline key={`e${i}`} positions={[nodes[e.a], nodes[e.b]]} pathOptions={{ color: '#3a4858', weight: 2, opacity: 0.8 }}>
            <Tooltip sticky>{e.name || `${e.a}–${e.b}`} · ~{e.km} km (approximate)</Tooltip>
          </Polyline>
        ))}
        {closedEdges.map((e, i) => nodes[e.a] && nodes[e.b] && (
          <Polyline key={`c${i}`} positions={[nodes[e.a], nodes[e.b]]} pathOptions={{ color: '#ff5c5c', weight: 3, dashArray: '6 6' }}>
            <Tooltip sticky>CLOSED: {e.name || `${e.a}–${e.b}`}</Tooltip>
          </Polyline>
        ))}

        {Object.entries(unitsByZone).map(([zid, byRes]) => {
          const z = zoneInfo[zid]
          if (!z || !z.route || z.route.length < 2) return null
          const total = Object.values(byRes).reduce((s, a) => s + a.units, 0)
          return (
            <Polyline key={`r${zid}`} positions={z.route.map((n) => nodes[n]).filter(Boolean)}
                      pathOptions={{ color: urgencyColor(z.urgency), weight: 2 + Math.min(10, total) * 0.8, opacity: 0.85 }}>
              <Tooltip sticky>
                <b>Route D → {zid}</b> ({fmt(z.dist_km, 0)} km): {Object.values(byRes).map((a) => `${a.units} ${RES[a.resource].short}`).join(', ')}
              </Tooltip>
            </Polyline>
          )
        })}

        <Marker position={scenario.depot.coordinates} icon={depotIcon}><Tooltip permanent direction="right" offset={[10, 0]}>{scenario.depot.name}</Tooltip></Marker>
        {scenario.junctions.map((j) => (
          <Marker key={j.id} position={j.coordinates} icon={junctionIcon}><Tooltip>{j.id} {j.name}</Tooltip></Marker>
        ))}

        {scenario.zones.map((zone) => {
          const z = zoneInfo[zone.id]
          const color = z.reachable ? urgencyColor(z.urgency) : '#5b6673'
          const isSel = selected?.zone === zone.id
          return (
            <CircleMarker key={zone.id} center={zone.coordinates} radius={10 + Math.sqrt(zone.population) / 25}
                          pathOptions={{ color: isSel ? '#fff' : color, fillColor: color, fillOpacity: 0.55, weight: isSel ? 3 : 1.5, dashArray: z.reachable ? null : '4 4' }}
                          eventHandlers={{ click: () => onSelectZone(zone.id) }}>
              <Tooltip permanent direction="top" offset={[0, -8]} className="zone-label">
                <span style={{ fontWeight: 700 }}>{zone.id} {zone.name}</span> · {fmt(z.urgency, 1)}{!z.reachable && ' · UNREACHABLE'}
              </Tooltip>
              <Popup>
                <b>{zone.id} {zone.name}</b> — urgency {fmt(z.urgency, 1)} {z.critical && '(critical)'}<br />
                Depth {zone.flood_depth_m} m{z.deep_water && ' (deep water)'} · vulnerable {Math.round(zone.vulnerable_pct * 100)}% · pop {zone.population.toLocaleString()}<br />
                {z.reachable ? `Route ${fmt(z.dist_km, 0)} km via ${z.route.join('→')}` : 'No road access from the depot'}<br />
                {RESOURCES.map((r) => {
                  const a = unitsByZone[zone.id]?.[r]
                  return <div key={r}>{RES[r].label}: {a ? `${a.units} units → ${a.served}/${a.demand}` : `0 units (${z.demand[r]} ${RES[r].demand})`}</div>
                })}
              </Popup>
            </CircleMarker>
          )
        })}
      </MapContainer>
      <div className="legend">
        <span><i className="sw" style={{ background: urgencyColor(20) }} />low urgency</span>
        <span><i className="sw" style={{ background: urgencyColor(60) }} />critical ≥ 60</span>
        <span><i className="sw" style={{ background: urgencyColor(95) }} />extreme</span>
        <span><i className="sw" style={{ background: '#5b6673' }} />unreachable</span>
        <span><i className="ln" style={{ borderColor: '#3a4858' }} />road (approx. km)</span>
        <span><i className="ln" style={{ borderColor: '#ff5c5c', borderStyle: 'dashed' }} />closed</span>
        <span><i className="ln" style={{ borderColor: urgencyColor(70), borderTopWidth: 5 }} />assigned route (width ∝ units)</span>
        <span>◆ State EOC (depot)</span>
      </div>
    </div>
  )
}
