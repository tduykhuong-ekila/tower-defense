import { forwardRef, useEffect, useImperativeHandle, useMemo, useState } from "react";
import { CameraFrame, RenderTeam, SceneMetrics } from "../../game/bridge";
import { battlefieldWorld, minimapPoint, minimapViewport, PALETTE, projectMap, routeToTeam, ServerMap, teamLabel, movementEdges } from "../../game/map";

interface DirectoryProps { teams: RenderTeam[]; ownId: string | null; targetId: string; onSelect: (id: string) => void; }
export function TeamDirectory({ teams, ownId, targetId, onSelect }: DirectoryProps) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("HP");
  const [filter, setFilter] = useState("ALL");
  const rows = teams.map((team, index) => ({team, index})).filter(({team, index}) =>
    `${index+1} ${team.name}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()) &&
    (filter === "ALL" || (filter === "OWN" ? team.id === ownId : team.status !== "ELIMINATED" && (filter !== "ENEMIES" || team.id !== ownId)))
  ).sort((a,b) => sort === "HP" ? b.team.base_hp-a.team.base_hp || a.index-b.index : sort === "SCORE" ? (b.team.score || 0)-(a.team.score || 0) || a.index-b.index : a.index-b.index);
  return <div className="team-directory">
    <input aria-label="Tìm đội hoặc số đội" placeholder="Tìm tên hoặc số đội…" value={search} onChange={e => setSearch(e.target.value)} />
    <div className="directory-controls">
      <select aria-label="Lọc đội" value={filter} onChange={e => setFilter(e.target.value)}>
        <option value="ALL">Tất cả ({teams.length})</option><option value="ALIVE">Còn chiến đấu</option><option value="ENEMIES">Đối thủ còn sống</option><option value="OWN">Đội của bạn</option>
      </select>
      <select aria-label="Sắp xếp đội" value={sort} onChange={e => setSort(e.target.value)}><option value="HP">HP giảm dần</option><option value="SCORE">Điểm giảm dần</option><option value="NUMBER">Số đội</option></select>
    </div>
    <p className="directory-count">{rows.length} đội · Chọn để xem căn cứ hoặc đặt mục tiêu cho lính mới</p>
    <div className="directory-rows">{rows.map(({team:t,index:i}) => <button className={`drawer-team ${t.id === targetId ? "selected" : ""}`} key={t.id} onClick={() => onSelect(t.id)}>
      <b className="team-number" style={{color: PALETTE[i]}}>{teamLabel(i)}</b>
      <span><strong>{t.name} {t.id === ownId && "· BẠN"}</strong><small>{t.base_hp} HP · {t.score || 0} điểm · {t.status === "ELIMINATED" ? "Đã bị loại" : "Còn chiến đấu"}</small></span>
      {t.id === targetId && <span aria-label="Mục tiêu">◎</span>}
    </button>)}</div>
    {!rows.length && <p>Không có đội phù hợp.</p>}
  </div>;
}
export interface ArenaNavigationRef { camera: (frame: CameraFrame) => void; metrics: (metrics: SceneMetrics) => void; }
interface NavigationProps extends DirectoryProps { map: ServerMap; onNavigate: (x: number,y: number) => void; onFit: () => void; onOwn: () => void; onCombat: () => void; onZoomIn?: () => void; onZoomOut?: () => void; }
export const ArenaNavigation = forwardRef<ArenaNavigationRef, NavigationProps>((props, ref) => {
  const {map, teams, ownId, targetId, onSelect, onNavigate, onFit, onOwn, onCombat} = props;
  const [frame, setFrame] = useState<CameraFrame | null>(null);
  const [metrics, setMetrics] = useState<SceneMetrics | null>(null);
  const [collapsed, setCollapsed] = useState(() => window.matchMedia("(max-width: 700px), (max-height: 500px)").matches);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 700px), (max-height: 500px)");
    const compact = () => { if (media.matches) setCollapsed(true); };
    media.addEventListener("change", compact);
    return () => media.removeEventListener("change", compact);
  }, []);
  const showMetrics = new URLSearchParams(location.search).has("performance");
  useImperativeHandle(ref, () => ({ camera: setFrame, metrics: showMetrics ? setMetrics : () => {} }), [showMetrics]);
  const world = battlefieldWorld(map);
  const viewport = frame ? minimapViewport(world, frame) : null;
  const nodes = useMemo(() => projectMap(map), [map]);
  const edges = useMemo(() => movementEdges(map), [map]);
  const route = useMemo(() => ownId && targetId ? routeToTeam(map, ownId, targetId).map(id => {
    const n = nodes.get(id)!; return `${n.worldX},${n.worldY}`;
  }).join(" ") : "", [map, ownId, targetId, nodes]);
  return <aside className={`arena-navigation fantasy-frame ${collapsed ? "collapsed" : ""}`}>
    <button className="minimap-heading" onClick={() => setCollapsed(!collapsed)} aria-expanded={!collapsed}>BẢN ĐỒ · {teams.filter(t => t.status !== "ELIMINATED").length}/{teams.length} đội <span>{collapsed ? "+" : "−"}</span></button>
    {/* <div className="minimap-actions">
      <button aria-label="Phóng to" onClick={onZoomIn}>＋</button>
      <button aria-label="Thu nhỏ" onClick={onZoomOut}>−</button>
    </div> */}
    {!collapsed && <>
      <svg role="application" aria-label="Minimap: chọn căn cứ hoặc vị trí để di chuyển camera" viewBox={`${world.x} ${world.y} ${world.width} ${world.height}`} preserveAspectRatio="none" style={{ aspectRatio: `${world.width} / ${world.height}` }} tabIndex={0}
        onKeyDown={e => { if (!frame || !["ArrowUp","ArrowDown","ArrowLeft","ArrowRight"].includes(e.key)) return; e.preventDefault(); onNavigate(frame.x+frame.width/2+(e.key === "ArrowRight" ? 200 : e.key === "ArrowLeft" ? -200 : 0), frame.y+frame.height/2+(e.key === "ArrowDown" ? 200 : e.key === "ArrowUp" ? -200 : 0)); }}
        onPointerDown={e => { const box = e.currentTarget.getBoundingClientRect(); const point = minimapPoint(world, (e.clientX-box.left)/box.width, (e.clientY-box.top)/box.height); onNavigate(point.x, point.y); }}>
        <rect x={world.x} y={world.y} width={world.width} height={world.height} rx={50} fill="#506c40" />
        {edges.map(e => { const a=nodes.get(e.from)!,b=nodes.get(e.to)!;return <line key={`${e.from}-${e.to}`} x1={a.worldX} y1={a.worldY} x2={b.worldX} y2={b.worldY} stroke="#a5aa70" strokeWidth={world.width/240} />; })}
        <polyline points={route} stroke="#ffe39b" strokeWidth={world.width/200} fill="none" />
        {teams.map((t,i) => { const n=nodes.get(`node_base_t${i+1}`); if(!n)return null; const r=world.width/45;
          return <g key={t.id} role="button" tabIndex={0} aria-label={`Căn cứ ${i+1} ${t.name}${t.status === "ELIMINATED" ? " đã bị loại" : ""}`}
            onPointerDown={e => {e.stopPropagation(); onSelect(t.id);}}
            onKeyDown={e => {if(e.key === "Enter" || e.key === " "){ e.preventDefault();onSelect(t.id);}}}>
            <circle cx={n.worldX} cy={n.worldY} r={r} fill={t.status === "ELIMINATED" ? "#555" : PALETTE[i]} stroke={t.id===ownId ? "#fff" : t.id===targetId ? "#ffdf73" : "#263c31"} strokeWidth={r/4} />
            <text x={n.worldX} y={n.worldY+r*.35} textAnchor="middle" fontWeight="bold" fontSize={r*.8} fill="#132f2c">{t.status === "ELIMINATED" ? "×" : i+1}</text>
          </g>;
        })}
        {frame?.combat && <circle cx={frame.combat.x} cy={frame.combat.y} r={world.width/65} fill="#f39050" stroke="#ffe4a4" strokeWidth={world.width/400} />}
        {viewport && <rect {...viewport} fill="#ffffd410" stroke="#fff6ce" strokeWidth={world.width/280} pointerEvents="none" />}
      </svg>
      <div className="minimap-actions"><button onClick={() => { if (window.innerWidth < 700) setCollapsed(true); onFit(); }}>Toàn cảnh</button><button onClick={onOwn} disabled={!ownId}>Căn cứ tôi</button><button onClick={onCombat} disabled={!frame?.combat}>Giao tranh</button></div>
      <small>Viền trắng: bạn · vàng: mục tiêu · ×: bị loại</small>
    </>}
    {showMetrics && metrics && <output className="arena-metrics" data-testid="arena-metrics">{JSON.stringify(metrics)}</output>}
  </aside>;
});
