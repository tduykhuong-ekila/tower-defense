import { showBattleStars, starPoints, upgradeLevel } from "../upgradeLevel";
import { DEFAULT_SHIELD_PLACEMENT, placementCell, gridRect, gridAnchor, placementReason, GridCell } from "../placement";
import Phaser from "phaser";
import { controllableTroops, shouldStartArmyBox } from "../armySelection";
import { graphRange } from "../range";
import { MotionTrack } from "../systems/interpolation";
import { formationPosition } from "../systems/formationPosition";
import { coincidentKey, coincidentRepresentatives } from "../systems/crowd";
import { SmoothCameraController } from "../camera/SmoothCameraController";
import { CombatEvent } from "../../types/combat";
import {
  EMPTY_SCENE,
  RenderEntity,
  SceneCallbacks,
  SceneState,
} from "../bridge";
import {
  canPlaceTower,
  isPointerClick,
  PALETTE,
  projectMap,
  teamIndex,
  VisualNode,
  arenaWorld,
  battlefieldWorld,
  overviewCamera,
  teamLabel,
  routeToTeam,
  roadPath,
  WORLD,
} from "../map";
import { createTerrain, riverX } from "../rendering/terrain";
import { AimedTurret, bakeTurretTextures, vehicleHullTexture } from "../rendering/aimedTurret";
import { TankDrive } from "../rendering/tankDrive";
import { InfantryRifle } from "../rendering/infantryRifle";
import { infantryRunAnimation, infantryTexture } from "../entityArtwork";
import { AimPoint } from "../systems/turretAim";

interface EntityVisual {
  root: Phaser.GameObjects.Container;
  sprite: Phaser.GameObjects.Sprite;
  hp: Phaser.GameObjects.Graphics;
  stars: Phaser.GameObjects.Image;
  ring: Phaser.GameObjects.Ellipse;
  data: RenderEntity;
  paintedHp?: string;
  turret?: AimedTurret;
  drive?: TankDrive;
  rifle?: InfantryRifle;
}
export class BattleScene extends Phaser.Scene {
  private world = WORLD;
  private route!: Phaser.GameObjects.Graphics;
  private approachRoads!: Phaser.GameObjects.Graphics;
  private approachExtent?: {left:number;top:number;right:number;bottom:number};
  private lastCameraTick = 0;
  private lastMetricsTick = 0;
  private slowFrames = 0;
  private lastFrameWall = 0;
  private frameTimes: number[] = [];
  private combatPoint?: { x: number; y: number };
  private ripples: Phaser.GameObjects.Image[] = [];
  private state: SceneState = EMPTY_SCENE;
  private selectedArmy = new Set<string>();
  private nodes = new Map<string, VisualNode>();
  private visuals = new Map<string, EntityVisual>();
  private infantryPool: EntityVisual[] = [];
  private crowdRepresentatives = new Set<string>();
  private motions = new Map<string, MotionTrack>();
  private deaths = new Set<string>();
  private bases = new Map<string, Phaser.GameObjects.Container>();
  private markers = new Map<string, Phaser.GameObjects.Container>();
  private ghost!: Phaser.GameObjects.Image;
  private range!: Phaser.GameObjects.Graphics;
  private placement!: Phaser.GameObjects.Graphics;
  private placementLabel!: Phaser.GameObjects.Text;
  private touchCell?: GridCell;
  private mapKey = "";
  private vegetationOccupancy = "";
  private fitZoom = 1;
  private terrain?: ReturnType<typeof createTerrain>;
  private zoomController!: SmoothCameraController;
  private down = { x: 0, y: 0 };
  private selectionBox!: Phaser.GameObjects.Graphics;
  private selectionStart?: {x: number; y: number};
  private selectionAdditive = false;
  private panKey?: Phaser.Input.Keyboard.Key;
  private dragged = false;
  private multiTouch = false;
  private pinchDistance = 0;
  private playing = false;
  private playbackTimer?: Phaser.Time.TimerEvent;
  private playbackWatchdog?: ReturnType<typeof setTimeout>;
  private shots: Phaser.GameObjects.Ellipse[] = [];
  private damageLabels: Phaser.GameObjects.Text[] = [];
  private puffs: Phaser.GameObjects.Graphics[] = [];
  private entityOffsets = new Map<string, number>();
  private transient = new Set<Phaser.GameObjects.GameObject>();
  public callbacks: SceneCallbacks | null = null;

  constructor() {
    super("BattleScene");
  }
  create() {
    this.cameras.main.setBackgroundColor("#78934b");
    this.zoomController = new SmoothCameraController(this.cameras.main, () => this.updateCameraBounds());
    this.input.addPointer(1);
    this.panKey = this.input.keyboard?.addKey(Phaser.Input.Keyboard.KeyCodes.SPACE, false);
    this.input.mouse?.disableContextMenu();
    this.input.on("pointerdown", this.pointerDown, this);
    this.input.on("pointermove", this.pointerMove, this);
    this.input.on("pointerup", this.pointerUp, this);
    this.input.on("wheel", this.wheelZoom, this);
    this.input.keyboard?.on("keydown-ESC", this.cancelMapInteraction, this);
    this.scale.on("resize", this.resizeCamera, this);
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      this.input.off("pointerdown", this.pointerDown, this);
      this.input.off("pointermove", this.pointerMove, this);
      this.input.off("pointerup", this.pointerUp, this);
      this.input.off("wheel", this.wheelZoom, this);
      this.input.keyboard?.off("keydown-ESC", this.cancelMapInteraction, this);
      this.scale.off("resize", this.resizeCamera, this);
      this.zoomController.destroy();
      this.playbackTimer?.remove();
      clearTimeout(this.playbackWatchdog);
      this.callbacks = null;
    });
    this.createOverlays();
    this.resizeCamera();
    this.game.events.emit("battle-ready", this);
  }
  private pointerDown(p: Phaser.Input.Pointer) {
    if (p.rightButtonDown() && this.state.mode === "BUILD") {
      this.callbacks?.onCancelBuild?.(); this.hideGhost(); return;
    }
    if (this.state.mode === "MODAL") return;
    if (!p.wasTouch) {
      // Map input owns keyboard focus; Space-pan must not activate a previously focused HUD button.
      this.game.canvas.tabIndex = -1;
      this.game.canvas.focus({ preventScroll: true });
    }
    this.zoomController.cancelPan();
    this.down = { x: p.x, y: p.y };
    this.dragged = false;
    this.multiTouch = this.input.pointer1.isDown && this.input.pointer2.isDown;
    this.selectionStart = undefined;
    if (this.multiTouch) {
      const a = this.input.pointer1, b = this.input.pointer2;
      this.pinchDistance = Phaser.Math.Distance.Between(a.x, a.y, b.x, b.y);
      this.selectionBox.clear();
      return;
    }
    const event = p.event as MouseEvent;
    if (shouldStartArmyBox({
      enabled: !!this.state.armyControlEnabled, mode: this.state.mode, touch: p.wasTouch,
      leftButton: p.leftButtonDown(), shift: !!event.shiftKey,
      boxTool: !!this.state.armySelectionMode, panKey: !!this.panKey?.isDown,
    })) {
      this.selectionStart = this.cameras.main.getWorldPoint(p.x, p.y);
      this.selectionAdditive = !!(event.shiftKey || event.ctrlKey || event.metaKey);
      this.hideGhost();
    }
  }

  private pointerUp(p: Phaser.Input.Pointer, over: Phaser.GameObjects.GameObject[] = []) {
    this.pinchDistance = 0;
    if (["MODAL", "WAITING"].includes(this.state.mode)) {
      this.selectionStart = undefined; this.selectionBox.clear(); return;
    }
    // Selection takes priority over deployment/building when Shift or the box tool is used.
    if (this.selectionStart) {
      if (this.dragged && !this.multiTouch) {
        const end = this.cameras.main.getWorldPoint(p.x, p.y);
        const rect = new Phaser.Geom.Rectangle(Math.min(end.x, this.selectionStart.x), Math.min(end.y, this.selectionStart.y),
          Math.abs(end.x-this.selectionStart.x), Math.abs(end.y-this.selectionStart.y));
        const ids = controllableTroops(this.state.entities, this.state.myTeamId).filter(e => {
          const visual = this.visuals.get(e.id);
          const node = this.nodes.get(e.current_node_id);
          const point = visual?.root || (node ? formationPosition(node, e.simulation_state, this.nodes) : null);
          return point && rect.contains(point.x, point.y);
        }).map(e => e.id);
        this.callbacks?.onArmySelect?.(ids, this.selectionAdditive, true);
      } else if (!over.length && this.clicked(p)) this.callbacks?.onArmySelect?.([], this.selectionAdditive);
      this.selectionStart = undefined;
      this.selectionBox.clear();
      return;
    }
    if (this.state.mode === "BUILD" && this.state.mapData?.placement_grid) {
      if (!this.dragged && !this.multiTouch && !p.rightButtonReleased() && isPointerClick(this.down,p)) {
        const point=this.cameras.main.getWorldPoint(p.x,p.y);
        const grid=this.state.mapData.placement_grid,footprint=grid.footprints[this.state.selectedUnit?.code || ""];
        if(!footprint) return;
        const cell=placementCell(grid,point.x,point.y,footprint);
        const valid=this.previewGrid(p);
        if (valid && (!p.wasTouch || (this.touchCell?.row===cell.row && this.touchCell?.col===cell.col))) {
          this.callbacks?.onGridClick?.(cell.row,cell.col); this.touchCell=undefined;
        } else if(p.wasTouch) this.touchCell=cell;
      }
      if (!this.input.pointer1.isDown && !this.input.pointer2.isDown) this.multiTouch=false;
      return;
    }
    if (p.rightButtonReleased()) {
      this.selectionStart = undefined;
      this.selectionBox.clear();
      if (!this.dragged && !this.multiTouch && isPointerClick(this.down, p) &&
          this.state.armyControlEnabled && this.selectedArmy.size) {
        const rect = this.game.canvas.getBoundingClientRect();
        this.callbacks?.onEntityInspect?.(null, 0, 0);
        this.callbacks?.onArmyContextMenu?.(
          rect.left + p.x * rect.width / this.scale.width,
          rect.top + p.y * rect.height / this.scale.height);
      }
      return;
    }
    if (!over.length && this.clicked(p)) {
      const event = p.event as MouseEvent;
      this.callbacks?.onArmySelect?.([], !!(event.shiftKey || event.ctrlKey || event.metaKey));
    }
    this.selectionStart = undefined;
    this.selectionBox.clear();
  }
  private cancelMapInteraction = () => {
    this.selectionStart = undefined;
    this.selectionBox?.clear();
    this.dragged = true; // A release after Escape must not turn into a click or a new selection.
    this.hideGhost();
  };
  private hideGhost() { this.ghost.setVisible(false); this.placement?.clear(); this.placementLabel?.setVisible(false); this.touchCell=undefined; }
  private previewGrid(p: Phaser.Input.Pointer) {
    const map=this.state.mapData,unit=this.state.selectedUnit,grid=map?.placement_grid;
    if(!map || !grid || !unit) return false;
    const point=this.cameras.main.getWorldPoint(p.x,p.y),footprint=grid.footprints[unit.code];
    if(!footprint) {this.hideGhost();return false;}
    const cell=placementCell(grid,point.x,point.y,footprint);
    const reason=placementReason(map,cell,unit.code,this.state.myTeamId || "",this.state.entities);
    const color=reason ? 0xe56858 : 0x91df99,rect=gridRect(grid,cell,footprint),anchor=gridAnchor(grid,cell,footprint);
    this.placement.clear().lineStyle(1,0xd2e5b4,.2);
    // Only a small neighborhood, never an object per arena cell.
    for(let r=Math.max(0,cell.row-2);r<=Math.min(grid.rows,cell.row+footprint.heightCells+2);r++)
      this.placement.lineBetween(Math.max(0,rect.x-64),grid.originY+r*grid.cellSize,Math.min(grid.cols*grid.cellSize,rect.x+rect.width+64),grid.originY+r*grid.cellSize);
    for(let c=Math.max(0,cell.col-2);c<=Math.min(grid.cols,cell.col+footprint.widthCells+2);c++)
      this.placement.lineBetween(grid.originX+c*grid.cellSize,Math.max(0,rect.y-64),grid.originX+c*grid.cellSize,Math.min(grid.rows*grid.cellSize,rect.y+rect.height+64));
    this.placement.fillStyle(color,.18).lineStyle(2,color,.85).fillRect(rect.x,rect.y,rect.width,rect.height).strokeRect(rect.x,rect.y,rect.width,rect.height);
    this.ghost.setTexture(this.texture(unit.code,teamIndex(map,this.state.myTeamId || ""),unit.level || 1))
      .setOrigin(.5,.89).setDisplaySize(94,94).setPosition(anchor.x,anchor.y).setTint(color).setAlpha(.6).setVisible(true);
    this.placementLabel.setText(reason || `${unit.cost} xu · ${p.wasTouch ? "Chạm lại ô này để xây" : "Nhấp để xây"}`)
      .setPosition(rect.x+rect.width/2,rect.y+rect.height+8).setColor(reason ? "#ffb5a6" : "#dbffd0").setVisible(true);
    this.range.clear().lineStyle(1.5, color,.4).strokeEllipse(anchor.x,anchor.y,unit.range*80*1.5*2,unit.range*80*.86*2);
    return !reason;
  }
  private wheelZoom(p: Phaser.Input.Pointer, _objects: unknown[], _dx: number, dy: number) {
    this.zoomController.wheel(dy, { x: p.x, y: p.y });
  }
  public zoomIn() { this.zoomController.step(1); }
  public zoomOut() { this.zoomController.step(-1); }
  private createOverlays() {
    this.selectionBox = this.add.graphics().setDepth(5300);
    this.placement=this.add.graphics().setDepth(5050).setName("grid-placement");
    this.placementLabel=this.add.text(0,0,"",{fontSize:"14px",backgroundColor:"#243d2ee8",padding:{x:6,y:4},wordWrap:{width:290}}).setOrigin(.5,0).setDepth(5200).setVisible(false).setName("placement-label");
    this.route = this.add.graphics().setDepth(-1);
    this.approachRoads = this.add.graphics().setDepth(-2);
    this.range = this.add.graphics().setDepth(5000);
    this.ghost = this.add
      .image(0, 0, "mg_tower")
      .setOrigin(0.5, 0.88)
      .setAlpha(0.55)
      .setDepth(5100)
      .setVisible(false);
  }
  public fit = (immediate = false) => {
    const c = this.cameras.main;
    c.panEffect.reset();
    const overview = overviewCamera(this.scale.width, this.scale.height, battlefieldWorld(this.state.mapData));
    this.fitZoom = overview.zoom;
    c.setViewport(0, 0, this.scale.width, this.scale.height);
    this.zoomController.setLimits(this.fitZoom, Math.max(1.5, this.fitZoom * 2.7));
    this.zoomController.moveTo(overview.centerX, overview.centerY, this.fitZoom, immediate);
  };
  private resizeCamera = () => {
    // Initial layout and viewport changes may reset immediately; user actions always animate.
    this.fit(true);
    if (this.scale.width < 600) this.focusBase();
  };
  private updateCameraBounds() {
    const c = this.cameras.main;
    const overview = overviewCamera(this.scale.width, this.scale.height, battlefieldWorld(this.state.mapData));
    const world = battlefieldWorld(this.state.mapData);
    const x = Math.max(0, (c.width / c.zoom - world.width) / 2);
    const y = Math.max(0, (c.height / c.zoom - world.height) / 2);
    const blend = Phaser.Math.Clamp((1.25 - c.zoom / this.fitZoom) / 0.25, 0, 1);
    const left = world.x - x + (overview.bounds.x - world.x + x) * blend;
    const top = world.y - y + (overview.bounds.y - world.y + y) * blend;
    const right = world.x + world.width + x +
      (overview.bounds.x + overview.bounds.width - world.x - world.width - x) * blend;
    const bottom = world.y + world.height + y +
      (overview.bounds.y + overview.bounds.height - world.y - world.height - y) * blend;
    const extent = this.approachExtent;
    // Keep long existing deployment queues reachable; ground also fills those bounds.
    const queueLeft = extent ? extent.left - (extent.left < world.x ? c.width / c.zoom / 2 : 0) : left;
    const queueTop = extent ? extent.top - (extent.top < world.y ? c.height / c.zoom / 2 : 0) : top;
    const queueRight = extent ? extent.right + (extent.right > world.x + world.width ? c.width / c.zoom / 2 : 0) : right;
    const queueBottom = extent ? extent.bottom + (extent.bottom > world.y + world.height ? c.height / c.zoom / 2 : 0) : bottom;
    const boundsLeft = Math.min(left, queueLeft), boundsTop = Math.min(top, queueTop);
    const width = Math.max(right, queueRight) - boundsLeft, height = Math.max(bottom, queueBottom) - boundsTop;
    c.setBounds(boundsLeft, boundsTop, width, height);
    this.terrain?.cover({ x: boundsLeft, y: boundsTop, width, height });
  }

  public focusBase(teamId = this.state.myTeamId || "") {
    const index = teamIndex(this.state.mapData, teamId);
    const n = this.nodes.get(`node_base_t${index + 1}`);
    if (n) this.zoomController.moveTo(n.worldX, n.worldY,
      Math.min(1.3, Math.max(0.8, this.fitZoom * (this.scale.width < 600 ? 2.7 : 1.8))));
  }
  public navigate(x: number, y: number, minimumZoom = 0) {
    this.zoomController.moveTo(x, y, Math.max(minimumZoom, this.zoomController.targetZoom));
  }
  public focusCombat() {
    if (this.combatPoint) this.navigate(this.combatPoint.x, this.combatPoint.y, 0.8);
  }
  private pointerMove(p: Phaser.Input.Pointer) {
    const a = this.input.pointer1,
      b = this.input.pointer2,
      c = this.cameras.main;
    if (a.isDown && b.isDown) {
      this.multiTouch = true;
      this.selectionStart = undefined;
      this.selectionBox.clear();
      const distance = Phaser.Math.Distance.Between(a.x, a.y, b.x, b.y);
      if (this.pinchDistance && distance > 0)
        this.zoomController.zoomTo(this.zoomController.targetZoom * distance / this.pinchDistance,
          { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
      this.pinchDistance = distance;
      return;
    }
    if (this.state.mode === "MODAL") return;
    if (p.isDown) {
      if (!isPointerClick(this.down, p)) this.dragged = true;
      if (this.selectionStart) {
        const end = c.getWorldPoint(p.x, p.y);
        this.selectionBox.clear().fillStyle(0x8edbb7, .14).lineStyle(1.5 / c.zoom, 0xbfe8bb, .9)
          .fillRect(this.selectionStart.x, this.selectionStart.y, end.x-this.selectionStart.x, end.y-this.selectionStart.y)
          .strokeRect(this.selectionStart.x, this.selectionStart.y, end.x-this.selectionStart.x, end.y-this.selectionStart.y);
        return;
      }
      if (this.dragged) {
        this.zoomController.cancelPan();
        c.scrollX -= (p.x - p.prevPosition.x) / c.zoom;
        c.scrollY -= (p.y - p.prevPosition.y) / c.zoom;
        this.ghost.setVisible(false);
        this.range.clear();
      }
    }
    if (this.state.mode === "BUILD" && this.state.mapData?.placement_grid) {
      if (!p.isDown || !this.dragged) this.previewGrid(p);
      return;
    }
    if (
      !p.isDown &&
      this.state.selectedUnit &&
      (this.state.mode === "BUILD" || this.state.mode === "DEPLOY")
    ) {
      const position = c.getWorldPoint(p.x, p.y);
      const candidates = Array.from(this.nodes.values()).filter((n) =>
        this.isValidNode(n),
      );
      const nearest = candidates.sort(
        (a, b) =>
          Phaser.Math.Distance.Between(
            position.x,
            position.y,
            a.worldX,
            a.worldY,
          ) -
          Phaser.Math.Distance.Between(
            position.x,
            position.y,
            b.worldX,
            b.worldY,
          ),
      )[0];
      const near =
        nearest &&
        Math.hypot(position.x - nearest.worldX, position.y - nearest.worldY) <
          55;
      this.ghost.clearTint()
        .setTexture(
          this.texture(
            this.state.selectedUnit.code,
            teamIndex(this.state.mapData, this.state.myTeamId || ""),
            this.state.selectedUnit.level ?? 1,
          ),
        )
        .setDisplaySize(
          this.state.mode === "DEPLOY" ? 45 : 85,
          this.state.mode === "DEPLOY" ? 45 : 85,
        )
        .setPosition(
          near ? nearest.worldX : position.x,
          near ? nearest.worldY : position.y,
        )
        .setVisible(true)
        .setAlpha(near ? 0.65 : 0.25);
      this.range.clear();
      if (near && this.state.mapData) this.paintRange(nearest.id, this.state.selectedUnit.range);

    }
  }
  private paintRange(source: string, radius: number, simulation = {}) {
    if (!this.state.mapData) return;
    const state = simulation as import("../../types/unit").UnitSimulationState;
    const node=this.nodes.get(source);
    if((state.grid_placement || node?.node_type === "tower_slot") && node) {
      const p=formationPosition(node,state,this.nodes);
      this.range.clear().lineStyle(1.5,0xffe3a2,.65).strokeEllipse(p.x,p.y,radius*80*1.5*2,radius*80*.86*2);
      return;
    }
    const coverage = graphRange(this.state.mapData, source, radius, simulation);
    this.range.clear().fillStyle(0xf4dc91, .22).lineStyle(9, 0xffe3a2, .45);
    for (const segment of coverage.segments) {
      const a = this.nodes.get(segment.from)!, b = this.nodes.get(segment.to)!;
      this.range.lineBetween(a.worldX + (b.worldX-a.worldX)*segment.start,
        a.worldY + (b.worldY-a.worldY)*segment.start,
        a.worldX + (b.worldX-a.worldX)*segment.end,
        a.worldY + (b.worldY-a.worldY)*segment.end);
    }
    this.range.lineStyle(1, 0xffe3a2, .7);
    for (const id of coverage.nodes) {
      const n = this.nodes.get(id);
      if (n?.is_passable) {
        this.range.fillEllipse(n.worldX, n.worldY, 32, 19);
        this.range.strokeEllipse(n.worldX, n.worldY, 32, 19);
      }
    }
  }
  private clicked(p: Phaser.Input.Pointer, gameplay = false) {
    if (p.rightButtonReleased() || p.middleButtonReleased() || (gameplay && this.selectionStart)) return false;
    const clicked =
      !this.dragged &&
      isPointerClick(this.down, p, this.multiTouch) &&
      !["MODAL", "WAITING", ...(this.state.mode === "BUILD" && this.state.mapData?.placement_grid && !this.selectionStart ? ["BUILD"] : []), ...(gameplay ? ["COMBAT"] : [])].includes(this.state.mode);
    if (!this.input.pointer1.isDown && !this.input.pointer2.isDown)
      this.multiTouch = false;
    return clicked;
  }
  private isValidNode(n: VisualNode) {
    const idx = teamIndex(this.state.mapData, this.state.myTeamId || "");
    if (this.state.mode === "DEPLOY") return n.id === `node_spawn_t${idx + 1}`;
    return (
      this.state.mode === "BUILD" &&
      canPlaceTower(n.id, this.state.validTowerSlots, this.state.entities)
    );
  }
  public updateState(state: SceneState) {
    if (this.state.selectedUnit?.code !== state.selectedUnit?.code || this.state.selectedUnit?.level !== state.selectedUnit?.level || state.mode !== "BUILD") this.touchCell=undefined;
    this.state = state;
    this.selectedArmy = new Set(state.selectedArmyIds || []);
    const key = state.mapData ? `${state.mapData.arena?.key || state.mapData.num_teams}:${state.mapData.team_ids.join(",")}` : "";
    if (key && key !== this.mapKey) {
      this.mapKey = key;
      this.vegetationOccupancy = "";
      this.children.removeAll(true);
      this.visuals.clear();
      this.infantryPool = [];
      this.crowdRepresentatives.clear();
      this.approachExtent = undefined;
      this.motions.clear();
      this.deaths.clear();
      this.shots = []; this.damageLabels = []; this.puffs = [];
      this.transient.clear();
      this.bases.clear();
      this.markers.clear();
      this.world = arenaWorld(state.mapData!);
      this.ripples = [];
      this.nodes = projectMap(state.mapData!);
      this.terrain = createTerrain(this, state.mapData!, this.nodes);
      this.createOverlays();
      this.createMarkers();
      this.fit();
      if (this.scale.width < 600 || state.teams.length > 8) this.focusBase();
    }
    if (this.playing) { this.reconcileArrivals(); return; }
    this.reconcile();
  }
  private reconcileArrivals() {
    // Legacy replay may be throttled; purchases still appear immediately.
    for (const entity of this.state.entities) {
      if (entity.status === "DESTROYED" || this.visuals.has(entity.id)) continue;
      const node = this.nodes.get(entity.current_node_id);
      if (!node) continue;
      const offset = [...this.visuals.values()].filter(v => v.data.current_node_id === entity.current_node_id && v.data.entity_kind === entity.entity_kind).length;
      const position = formationPosition(node, entity.simulation_state, this.nodes);
      const formation = entity.simulation_state?.formation_order !== undefined;
      this.createEntity(entity,
        position.x + (!formation && entity.entity_kind === "UNIT" ? ((offset % 6) - 2.5) * 3.2 : 0),
        position.y + (!formation && entity.entity_kind === "UNIT" ? (Math.floor((offset % 30) / 6) - 2) * 3 : 0));
      if (entity.entity_kind === "TOWER") this.markers.get(node.id)?.setVisible(false);
    }
  }
  private createMarkers() {
    for (const n of this.nodes.values()) {
      if (!["tower_slot", "spawn"].includes(n.node_type) || (this.state.mapData?.placement_grid && n.node_type === "tower_slot")) continue;
      const root = this.add
        .container(n.worldX, n.worldY)
        .setDepth(n.worldY - 5);
      const color = Phaser.Display.Color.HexStringToColor(
        PALETTE[((n.team_index || 1) - 1) % PALETTE.length],
      ).color;
      root.add(
        this.add
          .ellipse(0, 3, 43, 27, 0xc6bc84, 0.6)
          .setStrokeStyle(2, 0x777e4c),
      );
      root.add(
        this.add
          .text(0, 0, n.node_type === "spawn" ? "↑" : "+", {
            fontFamily: "Arial, sans-serif",
            fontSize: "25px",
            color: "#f5e7ba",
            stroke: "#657044",
            strokeThickness: 2,
          })
          .setOrigin(0.5),
      );
      const halo = this.add
        .ellipse(0, 3, 51, 33, color, 0.15)
        .setStrokeStyle(2, color)
        .setName("halo")
        .setVisible(false);
      root.add(halo);
      if (n.node_type === "spawn") {
        // Existing cartoon banner identifies the persistent team rally gate.
        root.add(this.add.image(-23, -22, `banner-${(n.team_index || 1) - 1}`).setDisplaySize(26, 40));
      }
      root.setSize(56, 45).setInteractive({ useHandCursor: true });
      root.on("pointerup", (p: Phaser.Input.Pointer) => {
        if (this.clicked(p, true)) this.callbacks?.onNodeClick(n.id);
      });
      root.on("pointerover", () => {
        if (this.isValidNode(n)) root.setScale(1.1);
      });
      root.on("pointerout", () => root.setScale(1));
      this.markers.set(n.id, root);
    }
  }
  private reconcile() {
    const { teams, entities } = this.state;
    this.approachRoads.clear();
    const approaches = new Map<string, {x:number;y:number;distance:number}>();
    let stagingExtentChanged = false;
    for (const e of entities) {
      const node = this.nodes.get(e.current_node_id), distance = e.simulation_state?.staging_distance || 0;
      if (node && e.status !== "DESTROYED" && e.simulation_state?.world_position && e.simulation_state.movement_zone === "STAGING") {
        const p = formationPosition(node, e.simulation_state, this.nodes);
        const previous = this.approachExtent || {left:0,top:0,right:this.world.width,bottom:this.world.height};
        const extent = {left:Math.min(previous.left,p.x-90),top:Math.min(previous.top,p.y-90),
          right:Math.max(previous.right,p.x+90),bottom:Math.max(previous.bottom,p.y+90)};
        if (extent.left !== previous.left || extent.top !== previous.top || extent.right !== previous.right || extent.bottom !== previous.bottom) {
          this.approachExtent = extent;
          stagingExtentChanged = true;
        }
      }
      if (!node || !distance || e.status === "DESTROYED") continue;
      if (distance > (approaches.get(node.id)?.distance || 0)) {
        const p = formationPosition(node, e.simulation_state, this.nodes);
        approaches.set(node.id, {...p,distance});
      }
    }
    for (const [id, end] of approaches) {
      const start = this.nodes.get(id)!;
      this.approachRoads.lineStyle(30, 0xa58f58, .8).lineBetween(start.worldX,start.worldY,end.x,end.y);
      this.approachRoads.lineStyle(23, 0xc9b478, .95).lineBetween(start.worldX,start.worldY,end.x,end.y);
      const previous = this.approachExtent;
      this.approachExtent = {left:Math.min(previous?.left ?? 0,end.x-90), top:Math.min(previous?.top ?? 0,end.y-90),
        right:Math.max(previous?.right ?? this.world.width,end.x+90), bottom:Math.max(previous?.bottom ?? this.world.height,end.y+90)};
    }
    if (approaches.size || stagingExtentChanged) this.updateCameraBounds();
    this.route.clear().lineStyle(3, 0xf4d78c, 0.65);
    if (this.state.mapData && this.state.myTeamId && this.state.selectedTargetTeamId) {
      const path = routeToTeam(this.state.mapData, this.state.myTeamId, this.state.selectedTargetTeamId);
      for (let i = 1; i < path.length; i++) {
        const a = this.nodes.get(path[i-1])!, b = this.nodes.get(path[i])!;
        this.route.lineBetween(a.worldX, a.worldY, b.worldX, b.worldY);
      }
    }
    for (const team of teams) {
      const idx = teamIndex(this.state.mapData, team.id),
        node = this.nodes.get(`node_base_t${idx + 1}`);
      if (!node) continue;
      let root = this.bases.get(team.id);
      if (!root) {
        const shieldZone = this.state.mapData?.placement_grid?.shieldPlacement || DEFAULT_SHIELD_PLACEMENT;
        root = this.add
          .container(node.worldX, node.worldY)
          .setDepth(node.worldY);
        const halo = this.add
          .ellipse(0, 10, 110, 58, 0xf9db8b, 0.08)
          .setStrokeStyle(2, 0xf5d288)
          .setName("halo");
        root.add(halo);
        root.add(
          this.add
            .image(0, 0, `base-${idx}`)
            .setOrigin(0.5, 0.88)
            .setDisplaySize(137, 137)
            .setName("art"),
        );
        root.add(
          this.add
            .ellipse(0, shieldZone.offsetY, shieldZone.width, shieldZone.height, 0x83cbd4, 0.08)
            .setStrokeStyle(2, 0xb2e0de, 0.55)
            .setName("shield"),
        );
        root.add(this.add.graphics().setName("hp"));
        root.add(
          this.add
            .text(0, 32, `${teamLabel(idx)} · ${team.name}`, {
              fontFamily: "Arial, sans-serif",
              fontSize: "14px",
              fontStyle: "bold",
              color: "#fff1c6",
              stroke: "#3c5236",
              strokeThickness: 4,
            })
            .setOrigin(0.5)
            .setName("label"),
        );
        root
          .setSize(125, 135)
          .setInteractive(
            // Phaser adds the container display origin before hit testing.
            new Phaser.Geom.Rectangle(-0.5, -52.5, 126, 140),
            Phaser.Geom.Rectangle.Contains,
          );
        root.input!.cursor = "pointer";
        root.on("pointerup", (p: Phaser.Input.Pointer) => {
          if (this.clicked(p)) this.callbacks?.onBaseClick(team.id);
        });
        this.bases.set(team.id, root);
      }
      (root.getByName("halo") as Phaser.GameObjects.Ellipse).setVisible(
        team.id === this.state.selectedTargetTeamId ||
          team.id === this.state.selectedEntityId,
      );
      (root.getByName("shield") as Phaser.GameObjects.Ellipse).setVisible(
        team.base_shield > 0 || (team.id === this.state.myTeamId && this.state.mode === "BUILD" && this.state.selectedUnit?.code === "shield_generator"),
      );
      const art = root.getByName("art") as Phaser.GameObjects.Image;
      art.setAlpha(team.base_hp <= 0 ? 0.35 : 1);
      const hp = root.getByName("hp") as Phaser.GameObjects.Graphics;
      hp.clear()
        .fillStyle(0x354734)
        .fillRoundedRect(-40, 17, 80, 7, 3)
        .fillStyle(team.base_hp > 100 ? 0x9bc45e : 0xd56d50)
        .fillRoundedRect(
          -38,
          19,
          76 * Math.max(0, team.base_hp / team.initial_base_hp),
          3,
          1,
        );
    }
    const active = entities.filter((e) => e.status !== "DESTROYED").sort((a,b) => a.id.localeCompare(b.id));
    this.entityOffsets.clear();
    const ids = new Set(active.map((e) => e.id));
    this.visuals.forEach((_v, id) => {
      if (!ids.has(id) && !this.deaths.has(id)) {
        this.destroyVisual(id);
      }
    });
    const grouped = new Map<string, number>();
    active.forEach((e) => {
      const n = this.nodes.get(e.current_node_id);
      if (!n) return;
      const groupKey = `${n.id}:${e.entity_kind}`;
      const offset = grouped.get(groupKey) || 0;
      grouped.set(groupKey, offset + 1);
      this.entityOffsets.set(e.id, offset);
      const next = e.simulation_state?.next_node_id ? this.nodes.get(e.simulation_state.next_node_id) : undefined;
      const progress = Math.min(1, Math.max(0, e.simulation_state?.edge_progress || 0));
      const live = e.entity_kind === "UNIT" && e.simulation_state !== undefined;
      const formation = e.simulation_state?.formation_order !== undefined;
      const position = formationPosition(n, e.simulation_state, this.nodes);
      const x = formation ? position.x : position.x + (e.entity_kind === "UNIT" ? ((offset % 6) - 2.5) * 3.2 : 0),
        y = formation ? position.y : position.y + (e.entity_kind === "UNIT" ? (Math.floor((offset % 30) / 6) - 2) * 3 : 0);
      let v = this.visuals.get(e.id);
      if (!v) v = this.createEntity(e, x, y);
      const old = v.data;
      if (old.level !== e.level) {
        v.rifle?.cancel();
        v.stars.setTexture(this.starsTexture(e.level));
        const animation = v.sprite.anims.currentAnim;
        const walking = v.sprite.anims.isPlaying;
        v.sprite.stop().setTexture(this.bodyTexture(e.unit_code, teamIndex(this.state.mapData, e.team_id), e.level));
        v.drive?.setLevel(e.level);
        if (v.turret) {
          if (e.unit_code === "mg_tower") v.sprite.setCrop(0, 274, 512, 238);
          v.turret.setLevel(e.level);
        }
        if (walking && animation) v.sprite.play(infantryRunAnimation(e.level), true);
      }
      if (live && this.state.liveBattle) {
        let motion = this.motions.get(e.id);
        if (!motion) { motion = new MotionTrack(e.tick_interval_ms || 200); this.motions.set(e.id, motion); }
        const offsetX = formation ? 0 : x - position.x;
        const offsetY = formation ? 0 : y - position.y;
        const path = old.current_node_id !== e.current_node_id && this.state.mapData
          ? roadPath(this.state.mapData, old.simulation_state?.next_node_id || old.current_node_id, e.current_node_id) : [];
        const corners = (e.simulation_state?.world_position ? [] : path).map(id => this.nodes.get(id)).filter((node): node is VisualNode => !!node)
          .map(node => ({x:node.worldX + offsetX, y:node.worldY + offsetY}));
        if (e.simulation_state?.world_position) {
          corners.push(...(e.simulation_state.movement_path || []).slice(1, -1)
            .map(point => formationPosition(n, {world_position: point}, this.nodes)));
        }
        motion.push({x,y}, `${e.current_node_id}:${next?.id}:${progress}:${x}:${y}:${e.simulation_at || ""}`, performance.now(), corners, e.simulation_at ? Date.parse(e.simulation_at) : undefined);
      } else if (live) {
        this.motions.delete(e.id);
        v.sprite.stop();
        if (e.unit_code === "infantry") v.sprite.setTexture(infantryTexture(e.level)).setFrame(0);
        v.root.setPosition(x, y);
      }
      v.data = e;
      v.root.setDepth(y);
      v.sprite.setAlpha(e.status === "DISABLED" ? 0.4 : 1);
      if (!live && Math.hypot(v.root.x - x, v.root.y - y) > 2) {
        this.stopRootAnimation(v);
        this.tweens.add({
          targets: v.root,
          x,
          y,
          duration: 400,
          ease: "Sine.easeInOut",
        });
      }
      const armySelected = this.selectedArmy.has(e.id);
      const returning = e.simulation_state?.order === "RETREAT";
      v.ring.setVisible(e.id === this.state.selectedEntityId || !!armySelected || returning);
      v.ring.setStrokeStyle(armySelected ? 3 : 2, returning ? 0x8edbdd : Phaser.Display.Color.HexStringToColor(PALETTE[Math.max(0, teamIndex(this.state.mapData, e.team_id))]).color);
      this.paintHp(v, e.current_hp);
    });
    const vegetationOccupancy = active.filter(e => e.entity_kind !== "UNIT" && e.simulation_state?.grid_placement)
      .map(e => `${e.id}:${e.simulation_state!.grid_placement!.row}:${e.simulation_state!.grid_placement!.col}`).sort().join("|");
    if (this.state.mapData?.placement_grid && vegetationOccupancy !== this.vegetationOccupancy) {
      this.vegetationOccupancy = vegetationOccupancy;
      const grid = this.state.mapData.placement_grid;
      const footprints = active.filter(e => e.entity_kind !== "UNIT" && e.simulation_state?.grid_placement)
        .map(e => gridRect(grid, e.simulation_state!.grid_placement!, e.simulation_state!.grid_placement!));
      for (const object of this.children.list) {
        if (object.name !== "natural-vegetation") continue;
        const plant = object as Phaser.GameObjects.Image, bounds = plant.getBounds();
        plant.setVisible(!footprints.some(rect => Phaser.Geom.Intersects.RectangleToRectangle(bounds, new Phaser.Geom.Rectangle(rect.x, rect.y, rect.width, rect.height))));
      }
    }
    const occupiedSlots = new Set(entities.filter(e => e.entity_kind === "TOWER" && e.status !== "DESTROYED").map(e => e.current_node_id));
    this.markers.forEach((m, id) => {
      const n = this.nodes.get(id)!;
      const occupied = occupiedSlots.has(id);
      m.setVisible(
        !occupied &&
          (n.node_type === "tower_slot" || n.node_type === "spawn"),
      );
      (m.getByName("halo") as Phaser.GameObjects.Ellipse).setVisible(
        this.isValidNode(n),
      );
      m.setAlpha(this.state.mode === "BUILD" && !this.isValidNode(n) ? 0.3 : 1);
    });
    if (!["BUILD", "DEPLOY"].includes(this.state.mode)) {
      this.hideGhost();
      this.range.clear();
      const inspected = entities.find(e => e.id === this.state.selectedEntityId);
      const radius = inspected?.range ?? inspected?.simulation_state?.attack_range;
      if (inspected && radius !== undefined) this.paintRange(inspected.current_node_id, radius, inspected.simulation_state);
    }
  }
  private starsTexture(level: number) {
    const count = upgradeLevel(level), key = `upgrade-stars-${count}`;
    if (!this.textures.exists(key)) {
      const g = this.make.graphics({x: 0, y: 0});
      g.fillStyle(0xe6c779);
      for (let i = 0; i < count; i++) {
        g.fillPoints(starPoints(6 + i * 12, 6).map(([x, y]) => new Phaser.Geom.Point(x, y)), true);
      }
      g.generateTexture(key, 36, 12);
      g.destroy();
    }
    return key;
  }
  private texture(code: string, _index: number, level = 1) {
    if (code === "infantry") return infantryTexture(level);
    const key = code;
    const current = upgradeLevel(level);
    const upgraded = key + (current > 1 ? `-lv${current}` : "");
    return this.textures.exists(upgraded) ? upgraded : "mg_tower";
  }
  private bodyTexture(code: string, index: number, level = 1) {
    const current = upgradeLevel(level);
    if (code === "tank" || code === "artillery") {
      bakeTurretTextures(this, code, current, "hull");
      return vehicleHullTexture(current, code);
    }
    return code === "cannon_tower" ? `cannon_tower-base${current > 1 ? `-lv${current}` : ""}`
      : this.texture(code, index, current);
  }
  private createEntity(e: RenderEntity, x: number, y: number): EntityVisual {
    const idx = Math.max(0, teamIndex(this.state.mapData, e.team_id)),
      size =
        e.entity_kind === "TOWER" ? 94 : e.unit_code === "infantry" ? 43 : 68;
    const pooled = e.unit_code === "infantry" ? this.infantryPool.pop() : undefined;
    if (pooled) {
      pooled.rifle?.cancel();
      pooled.data = e;
      pooled.paintedHp = undefined;
      pooled.root.setAngle(0).setData("entityId", e.id).setPosition(x, y).setDepth(y)
        .setActive(true).setVisible(true).setAlpha(1).setScale(1);
      pooled.sprite.setAngle(0).setPosition(0, 0).setTexture(this.texture(e.unit_code, idx, e.level)).setAlpha(1).setFlipX(false);
      pooled.ring.setVisible(false);
      pooled.stars.setTexture(this.starsTexture(e.level)).setVisible(showBattleStars(e.unit_code, this.cameras.main.zoom));
      this.visuals.set(e.id, pooled);
      this.paintHp(pooled, e.current_hp);
      return pooled;
    }
    const root = this.add.container(x, y).setDepth(y).setData("entityId", e.id);
    const ring = this.add
      .ellipse(0, 1, size * 0.8, size * 0.32, 0xf6de99, 0.2)
      .setStrokeStyle(2, 0xf4d180)
      .setVisible(false);
    root.add(ring);
    const sprite = this.add
      .sprite(0, 0, this.bodyTexture(e.unit_code, idx, e.level))
      .setOrigin(0.5, 0.89)
      .setDisplaySize(size, size);
    root.add(sprite);
    const drive = e.unit_code === "tank" || e.unit_code === "artillery" ? new TankDrive(root, sprite, e.level, size, e.unit_code) : undefined;
    // Mobile chassis and upper assemblies have independent directional frames;
    // stationary towers keep their original PNG foundations.
    const turret = ["mg_tower", "cannon_tower", "tank", "artillery"].includes(e.unit_code)
      ? new AimedTurret(root, e.level, e.unit_code === "tank" || e.unit_code === "artillery" ? e.unit_code : e.unit_code === "cannon_tower" ? "cannon" : "machineGun", size) : undefined;
    if (e.unit_code === "mg_tower") sprite.setCrop(0, 274, 512, 238);
    const hp = this.add.graphics();
    root.add(hp);
    if (e.entity_kind === "TOWER")
      root.add(this.add.image(33, -28, `banner-${idx}`).setDisplaySize(38, 38));
    root
      .setSize(size, size)
      .setInteractive(
        // Align input with the sprite after Phaser adds the container origin.
        new Phaser.Geom.Rectangle(0, -size * 0.39, size, size),
        Phaser.Geom.Rectangle.Contains,
      );
    root.input!.cursor = "pointer";
    root.on("pointerup", (p: Phaser.Input.Pointer) => {
      if (this.clicked(p)) {
        const event = p.event as MouseEvent;
        this.callbacks?.onEntityClick(root.getData("entityId"), !!(event.shiftKey || event.ctrlKey || event.metaKey));
        if (p.wasTouch) inspect(p, true);
      }
    });
    const inspect = (p: Phaser.Input.Pointer, pinned = false) => {
      if (["MODAL", "BUILD", "DEPLOY"].includes(this.state.mode)) return;
      const rect = this.game.canvas.getBoundingClientRect();
      this.callbacks?.onEntityInspect?.(root.getData("entityId"),
        rect.left + p.x * rect.width / this.scale.width,
        rect.top + p.y * rect.height / this.scale.height, pinned);
    };
    root.on("pointerover", (p: Phaser.Input.Pointer) => { if (["BUILD","MODAL"].includes(this.state.mode)) return; ring.setVisible(true); if (!p.wasTouch) inspect(p); });
    root.on("pointerout", () => {
      const id = root.getData("entityId");
      ring.setVisible(this.state.selectedEntityId === id || this.selectedArmy.has(id) || this.visuals.get(id)?.data.simulation_state?.order === "RETREAT");
      this.callbacks?.onEntityInspect?.(null, 0, 0);
    });
    // Center the level stars just above the sprite, regardless of entity size.
    // Artillery can aim its elevated barrel straight toward the top of the view.
    const stars = this.add.image(0, e.unit_code === "artillery" ? -100 : -size * 0.89 - 12, this.starsTexture(e.level))
      .setDisplaySize(36, 12)
      .setVisible(showBattleStars(e.unit_code, this.cameras.main.zoom));
    root.add(stars);
    const v: EntityVisual = { root, sprite, hp, ring, stars, data: e, turret, drive };
    if (e.unit_code === "infantry") v.rifle = new InfantryRifle(root, sprite);
    this.visuals.set(e.id, v);
    this.paintHp(v, e.current_hp);
    if (e.unit_code === "infantry" && this.state.entities.length < 200)
      this.tweens.add({
        targets: sprite,
        y: -1.2,
        duration: 850 + idx * 40,
        yoyo: true,
        repeat: -1,
      });
    root.setAlpha(0).setScale(0.9);
    this.tweens.add({
      targets: root,
      alpha: 1,
      scaleX: 1,
      scaleY: 1,
      duration: 300,
      ease: "Back.easeOut",
    });
    return v;
  }
  private paintHp(v: EntityVisual, hp: number) {
    const key = `${hp}:${v.data.max_hp}:${v.data.team_id}`;
    if (v.paintedHp === key) return;
    v.paintedHp = key;
    const width = v.data.entity_kind === "TOWER" ? 43 : 27;
    const y =
      v.data.entity_kind === "TOWER"
        ? -82
        : v.data.unit_code === "artillery"
          ? -86
        : v.data.unit_code === "infantry"
          ? -40
          : -58;
    const color = Phaser.Display.Color.HexStringToColor(
      PALETTE[Math.max(0, teamIndex(this.state.mapData, v.data.team_id))],
    ).color;
    v.hp
      .clear()
      .fillStyle(0x344734)
      .fillRoundedRect(-width / 2 - 1, y - 1, width + 2, 5, 2)
      .fillStyle(color)
      .fillRect(
        -width / 2,
        y,
        width * Math.max(0, hp / Math.max(1, v.data.max_hp)),
        3,
      );
  }
  private destroyVisual(id: string) {
    this.motions.delete(id);
    this.deaths.delete(id);
    const v = this.visuals.get(id);
    if (v) {
      v.rifle?.cancel();
      v.turret?.destroy();
      this.tweens.killTweensOf(v.root);
      this.tweens.killTweensOf(v.sprite);
      v.sprite.stop();
      if (v.data.unit_code === "infantry" && this.infantryPool.length < 128) {
        v.root.setActive(false).setVisible(false);
        this.infantryPool.push(v);
      } else v.root.destroy();
      this.visuals.delete(id);
    }
  }
  private stopRootAnimation(v: EntityVisual) {
    // Keep destruction callbacks alive so they can release the visual/pool slot.
    if (this.deaths.has(v.data.id)) return;
    this.tweens.killTweensOf(v.root);
    // Position/replay tweens share the root with the spawn fade. Cancelling
    // that fade before its first frame otherwise leaves a living entity at
    // alpha=0 forever, even after authoritative snapshots reconcile it.
    if (v.data.status !== "DESTROYED")
      v.root.setAlpha(1).setScale(1).setAngle(0);
  }
  public playLiveEvents(events: CombatEvent[]) {
    for (const event of events.slice(0, 160)) {
      if (event.type === "ENTITY_DESTROYED" && event.entity_id) {
        const id = event.entity_id, v = this.visuals.get(id);
        this.motions.delete(id);
        if (v && !this.deaths.has(id)) {
          this.deaths.add(id);
          this.tweens.add({targets:v.root, alpha:0, scale:.6, duration:180, onComplete:() => this.destroyVisual(id)});
        }
      } else if (event.type !== "UNIT_MOVED") this.animateEvent(event, 180);
    }
  }
  public playCombatEvents(events: CombatEvent[]) {
    if (!events.length) return;
    // A newer round supersedes a throttled replay; never accumulate a backlog.
    if (this.playing) this.skipCombat();
    this.playing = true;
    this.playbackWatchdog = setTimeout(() => this.skipCombat(), 8000);
    this.callbacks?.onPlaybackChange(true);
    this.ghost.setVisible(false);
    this.range.clear();
    const batches = Math.min(events.length, Math.ceil(7000 / 32));
    const batchSize = Math.ceil(events.length / batches);
    const duration = Math.min(320, 7000 / batches);
    let cursor = 0;
    this.playbackTimer = this.time.addEvent({
      delay: duration,
      repeat: Math.ceil(events.length / batchSize),
      callback: () => {
        if (cursor < events.length) {
          for (let i = 0; i < batchSize && cursor < events.length; i++)
            this.animateEvent(events[cursor++], Math.max(80, duration));
        } else this.finishPlayback();
      },
    });
  }
  private animateEvent(e: CombatEvent, duration: number) {
    const id = e.entity_id || e.unit_id || e.attacker_id || e.tower_id;
    const actor = id ? this.visuals.get(id) : null;
    if (e.type === "UNIT_MOVED" && actor && e.to_node) {
      const n = this.nodes.get(e.to_node);
      if (n) {
        actor.rifle?.cancel();
        if (actor.data.unit_code === "infantry")
          actor.sprite.play(infantryRunAnimation(actor.data.level));
        if (!actor.drive) actor.sprite.setFlipX(n.worldX < actor.root.x);
        this.stopRootAnimation(actor);
        this.tweens.add({
          targets: actor.root,
          x: n.worldX,
          y: n.worldY,
          duration: duration * 0.9,
          onUpdate: () => actor.root.setDepth(actor.root.y),
          onComplete: () => {
            actor.sprite.stop();
            if (actor.data.unit_code === "infantry") actor.sprite.setTexture(infantryTexture(actor.data.level)).setFrame(0);
          },
        });
      }
    }
    if (["TOWER_ATTACKED", "UNIT_ATTACKED", "BASE_DAMAGED"].includes(e.type)) {
      const target = e.target_entity_id
        ? this.visuals.get(e.target_entity_id)?.root
        : this.bases.get(e.target_team_id || "");
      if (target) this.combatPoint = { x: target.x, y: target.y };
      const aimId = e.target_entity_id || (e.target_team_id ? `base:${e.target_team_id}` : undefined);
      if (actor?.turret && aimId && target)
        actor.turret.trackTarget(aimId, this.time.now);
      if (actor && target && this.cameras.main.zoom >= 0.4) {
        if (actor.rifle) {
          actor.rifle.fire(teamIndex(this.state.mapData, actor.data.team_id), actor.data.level, target);
          this.launchShot(actor, target, duration, actor.rifle.muzzle());
        } else if (actor.turret && aimId) {
          actor.turret.fire(aimId, this.time.now,
            muzzle => this.launchShot(actor, target, duration, muzzle));
        } else {
          this.tweens.add({targets: actor.sprite, angle: -7, duration: 65, yoyo: true});
          this.launchShot(actor, target, duration);
        }
        this.combatPoint = { x: target.x, y: target.y };
      }
      if (target && this.cameras.main.zoom >= 0.4) {
        const dmg = e.hp_damage ?? e.damage ?? 0;
        const text = this.damageLabels.find(o => !o.active) || (this.damageLabels.length < 24 ? this.add.text(0, 0, "", {fontFamily:"Arial, sans-serif",fontSize:"20px",fontStyle:"bold",color:"#fff0ba",stroke:"#8b4636",strokeThickness:4}).setOrigin(.5).setDepth(7000) : null);
        if (text) {
        if (!this.damageLabels.includes(text)) this.damageLabels.push(text);
        text.setText(`−${dmg}`).setActive(true).setVisible(true).setPosition(target.x,target.y-45).setAlpha(1);
        this.transient.add(text);
        this.tweens.add({
          targets: text,
          y: target.y - 80,
          alpha: 0,
          duration: 800,
          onComplete: () => {
            this.transient.delete(text);
            text.setActive(false).setVisible(false);
          },
        });
        }
        const visual = e.target_entity_id
          ? this.visuals.get(e.target_entity_id)
          : null;
        if (visual && e.target_hp_remaining !== undefined)
          this.paintHp(visual, e.target_hp_remaining);
      }
    }
    if (e.type === "ENTITY_DESTROYED" && actor) {
      this.impact(actor.root.x, actor.root.y - 10);
      actor.sprite.stop();
      this.tweens.add({
        targets: actor.root,
        alpha: 0,
        angle: 20,
        duration: Math.min(duration, 250),
        onComplete: () => this.destroyVisual(e.entity_id!),
      });
    }
    if (e.type === "BASE_DESTROYED") {
      const base = this.bases.get(e.team_id || "");
      if (base) {
        this.impact(base.x, base.y - 30);
        base.setAlpha(0.4);
      }
    }
    if (e.type === "SHIELD_GENERATED" || e.type === "SHIELD_EXPIRED") {
      const shield = this.bases.get(e.team_id || "")?.getByName("shield") as
        | Phaser.GameObjects.Ellipse
        | undefined;
      shield?.setVisible(e.type === "SHIELD_GENERATED");
    }
  }
  private launchShot(actor: EntityVisual, target: Phaser.GameObjects.Container, duration: number, muzzle?: AimPoint) {
    if (!actor.root.active || !target.active || this.cameras.main.zoom < .4) return;
    const shot = this.shots.find(o => !o.active) || (this.shots.length < 16
      ? this.add.ellipse(0, 0, 9, 7, 0xeec270).setStrokeStyle(2, 0x6d5738).setDepth(6000) : null);
    if (!shot) return;
    if (!this.shots.includes(shot)) this.shots.push(shot);
    shot.setActive(true).setVisible(true).setPosition(muzzle?.x ?? actor.root.x, muzzle?.y ?? actor.root.y - 25).setAlpha(1);
    const impact = {x: target.x, y: target.y - 20};
    this.transient.add(shot);
    this.tweens.add({targets: shot, ...impact, duration: Math.min(220, duration * .6), onComplete: () => {
      this.transient.delete(shot); shot.setActive(false).setVisible(false);
      this.impact(impact.x, impact.y);
    }});
  }
  private impact(x: number, y: number) {
    this.combatPoint = { x, y };
    if (this.transient.size >= 48 || this.cameras.main.zoom < 0.4) return;
    const puff = this.puffs.find(o => !o.active) || (this.puffs.length < 12 ? this.add.graphics().setDepth(6200) : null);
    if (!puff) return;
    if (!this.puffs.includes(puff)) this.puffs.push(puff);
    puff.clear().setActive(true).setVisible(true).setPosition(x,y).setScale(1).setAlpha(1);
    this.transient.add(puff);
    for (let i = 0; i < 6; i++) {
      puff.fillStyle(i % 2 ? 0xe8be74 : 0xd99559, 0.8);
      puff.fillCircle(Math.cos(i) * 9, Math.sin(i) * 8, 7);
    }
    this.tweens.add({
      targets: puff,
      scaleX: 1.8,
      scaleY: 1.8,
      alpha: 0,
      duration: 350,
      onComplete: () => {
        this.transient.delete(puff);
        puff.setActive(false).setVisible(false);
      },
    });
  }
  private finishPlayback() {
    clearTimeout(this.playbackWatchdog);
    this.playbackTimer?.remove();
    this.playing = false;
    // Recovery snapshots also call skipCombat. Only legacy replay owns root
    // tweens/animation stops; a live snapshot must preserve locomotion phase.
    if (!this.state.liveBattle) for (const v of this.visuals.values()) {
      this.stopRootAnimation(v);
      v.sprite.stop();
      if (v.data.unit_code === "infantry") v.sprite.setTexture(infantryTexture(v.data.level)).setFrame(0);
    }
    this.reconcile();
    this.callbacks?.onPlaybackChange(false);
  }
  public skipCombat() {
    for (const v of this.visuals.values()) v.rifle?.cancel();
    this.transient.forEach((o) => {
      this.tweens.killTweensOf(o);
      o.setActive(false);
      (o as Phaser.GameObjects.Ellipse).setVisible(false);
    });
    this.transient.clear();
    this.finishPlayback();
  }
  update(time: number, delta: number) {
    if (this.state.liveBattle) {
      const now = performance.now();
      for (const [id, motion] of this.motions) {
        const v = this.visuals.get(id), p = motion.at(now);
        if (v && p && !this.deaths.has(id)) {
          const moving = Math.hypot(p.x - v.root.x, p.y - v.root.y) > .01;
          if (moving && !v.drive && !v.rifle?.attacking) v.sprite.setFlipX(p.x < v.root.x);
          if (v.data.unit_code === "infantry" && v.root.visible && !v.rifle?.attacking) {
            const key = infantryRunAnimation(v.data.level);
            // Packet gaps and viewport pauses are not locomotion transitions.
            const walking = moving || v.data.simulation_state?.movement_state === "MOVING";
            if (walking && (v.sprite.anims.currentAnim?.key !== key ||
                (!v.sprite.anims.isPlaying && !v.sprite.anims.isPaused))) v.sprite.play(key, true);
            else if (!walking && (v.sprite.anims.isPlaying || v.sprite.anims.isPaused)) {
              v.sprite.stop().setTexture(infantryTexture(v.data.level)).setFrame(0);
            }
          }
          v.root.setPosition(p.x, p.y).setDepth(p.y);
        }
      }
    }
    const locateTarget = (id: string) => {
      if (id.startsWith("base:")) {
        const teamId = id.slice(5), team = this.state.teams.find(t => t.id === teamId);
        return team && team.base_hp > 0 && team.status !== "ELIMINATED" ? this.bases.get(teamId) : undefined;
      }
      const target = this.visuals.get(id);
      return target && target.data.current_hp > 0 && target.data.status !== "DESTROYED" && !this.deaths.has(id)
        ? target.root : undefined;
    };
    for (const [id, v] of this.visuals) {
      const active = v.data.status === "ACTIVE" && v.data.current_hp > 0 && !this.deaths.has(id);
      v.rifle?.update(delta, active, teamIndex(this.state.mapData, v.data.team_id), v.data.level);
      v.drive?.update(delta, active);
      if (v.turret) {
        if (v.drive) v.turret.setHullYaw(v.drive.yaw);
        v.turret.update(delta, time, v.data.simulation_state?.attack_target_id, active, locateTarget);
      }
    }
    this.zoomController.update(delta);
    if(this.state.mode === "BUILD" && this.state.mapData?.placement_grid && !this.dragged && !this.multiTouch)
      this.previewGrid(this.input.activePointer);
    const wall = performance.now();
    const elapsed = this.lastFrameWall ? wall - this.lastFrameWall : 0;
    this.lastFrameWall = wall;
    if (elapsed > 0) this.frameTimes.push(elapsed);
    if (!this.lastMetricsTick) this.lastMetricsTick = wall;
    const c = this.cameras.main;
    if (elapsed > 33.4) this.slowFrames++;
    if (time - this.lastCameraTick > 100) {
      this.lastCameraTick = time;
      const view = c.worldView;
      const bounds = new Phaser.Geom.Rectangle(view.x - 180, view.y - 180, view.width + 360, view.height + 360);
      // Measured large-army overdraw: omit only bodies at the exact same
      // authoritative position. Every distinct position and selected ID stays.
      const representatives = this.visuals.size >= 200
        ? coincidentRepresentatives(this.visuals.values(), this.crowdRepresentatives) : null;
      this.crowdRepresentatives = representatives || new Set();
      for (const v of this.visuals.values()) {
        const bodyVisible = !representatives || coincidentKey(v.data) === null || representatives.has(v.data.id);
        const visible = bounds.contains(v.root.x, v.root.y) &&
          (v.data.entity_kind === "TOWER" || v.data.id === this.state.selectedEntityId || this.selectedArmy.has(v.data.id) ||
           bodyVisible);
        v.root.setVisible(visible);
        v.hp.setVisible(c.zoom >= 0.5);
        v.stars.setVisible(visible && showBattleStars(v.data.unit_code, c.zoom));
        if (!visible) v.sprite.anims.pause();
        else v.sprite.anims.resume();
        for (const tween of this.tweens.getTweensOf(v.sprite)) {
          if (visible) tween.resume(); else tween.pause();
        }
      }
      for (const [id, base] of this.bases) {
        const label = base.getByName("label") as Phaser.GameObjects.Text;
        const idx = teamIndex(this.state.mapData, id);
        const name = this.state.teams.find(t => t.id === id)?.name || "";
        label.setText(c.zoom < 0.5 ? teamLabel(idx) : `${teamLabel(idx)} · ${name}`);
        label.setScale(Math.max(1, 0.8 / c.zoom));
      }
      this.callbacks?.onCameraChange?.({ x: view.x, y: view.y, width: view.width, height: view.height, combat: this.combatPoint });
    }
    if (wall - this.lastMetricsTick > 1000) {
      const fps = Math.round(this.frameTimes.length * 1000 / (wall - this.lastMetricsTick));
      const frameTimes = this.frameTimes.sort((a,b) => a-b);
      const frameMsMax = Math.round(Math.max(...frameTimes) * 10) / 10;
      const frameMsP95 = Math.round((frameTimes[Math.floor(frameTimes.length * 0.95)] || 0) * 10) / 10;
      this.frameTimes = [];
      this.lastMetricsTick = wall;
      let textureBytes = 0;
      for (const key of this.textures.getTextureKeys()) for (const src of this.textures.get(key).source)
        textureBytes += src.width * src.height * 4;
      this.callbacks?.onMetrics?.({ fps, serverEntities: this.state.entities.length, entities: this.visuals.size,
        visibleEntities: [...this.visuals.values()].filter(v => v.root.visible).length,
        objects: this.children.length, effects: this.transient.size, slowFrames: this.slowFrames, frameMsMax, frameMsP95,
        textureMB: Math.round(textureBytes / 1048576 * 10) / 10 });
    }
    // Water highlights animate independently; no React render or state simulation per frame.
    if (!this.mapKey) return;
    if (!this.textures.exists("water-glint")) {
      const g = this.make.graphics({ x: 0, y: 0 });
      g.lineStyle(2, 0xd5eee2, 0.5).lineBetween(0, 2, 9, 0);
      g.generateTexture("water-glint", 12, 4);
      g.destroy();
    }
    if (!this.ripples.length)
      for (let i = 0; i < 24; i++) this.ripples.push(this.add.image(0, 0, "water-glint").setDepth(-900));
    this.ripples.forEach((ripple, i) => {
      const y = (i * this.world.height / 24 + time * 0.012) % this.world.height;
      ripple.setPosition(riverX(y, this.world,
        this.state.mapData?.placement_grid?.riverOffsetX ?? 0,
        this.state.mapData?.placement_grid?.riverPath) + Math.sin(i) * 17, y)
        .setAlpha(0.2 + Math.sin(time * 0.002 + i) * 0.15);
    });
  }
}
