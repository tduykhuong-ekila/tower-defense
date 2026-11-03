import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MaximumTeamsSelect, maxTeamOptions } from '../src/components/MaximumTeamsSelect';
import { activeMemberCount, teamHasPlayers } from '../src/game/teamMembership';
import { CameraPort, SmoothCameraController } from '../src/game/camera/SmoothCameraController';
import type { Team } from '../src/types/match';

const constraints = { min_teams_to_start: 2, max_teams: 20, default_max_teams: 4, min_members_per_team: 1 };
test('maximum capacity select uses server bounds, defaults to four and has no minimum input', () => {
  const html = renderToStaticMarkup(React.createElement(MaximumTeamsSelect, { constraints, onChange: () => {} }));
  assert.equal((html.match(/<option /g) || []).length, 19);
  assert.match(html, /value="4" selected/);
  assert.match(html, /Maximum Teams/);
  assert.doesNotMatch(html, /<input|Minimum Teams/);
  assert.deepEqual(maxTeamOptions({ ...constraints, max_teams: 6 }), [2,3,4,5,6]);
  assert.equal(maxTeamOptions(constraints, 6)[0], 6);
});
test('one mentor or mentee suffices; empty, spectators and foreign team members do not', () => {
  const team = { id: 't1', members: [] } as unknown as Team;
  assert.equal(teamHasPlayers(team), false);
  for (const role of ['MENTOR', 'MENTEE'] as const) {
    team.members = [{ id: 'm1', team_id: 't1', role }] as Team['members'];
    assert.equal(teamHasPlayers(team), true);
  }
  team.members.push({ team_id: 't1', role: 'MENTEE' } as Team['members'][number]);
  assert.equal(activeMemberCount(team), 2);
  team.members = [{ team_id: 't1', role: 'SPECTATOR' }, { team_id: 'other', role: 'MENTEE' }] as Team['members'];
  assert.equal(teamHasPlayers(team), false);
});

function setup() {
  const camera: CameraPort = { x: 0, y: 0, width: 1000, height: 600, originX: 0.5, originY: 0.5,
    zoom: 1, scrollX: 500, scrollY: 500, setZoom(z) { this.zoom = z; },
    clampX: x => Math.max(-1000, Math.min(3000, x)), clampY: y => Math.max(-1000, Math.min(3000, y)) };
  const controller = new SmoothCameraController(camera, () => {});
  controller.setLimits(0.25, 2);
  return { camera, controller };
}
function worldAt(c: CameraPort, x: number, y: number) {
  return { x: c.scrollX + c.width / 2 + (x - c.x - c.width / 2) / c.zoom,
    y: c.scrollY + c.height / 2 + (y - c.y - c.height / 2) / c.zoom };
}
test('zoom is deferred, monotonic, clamped and converges without overshooting after rapid input', () => {
  const { camera: c, controller: ctrl } = setup();
  for (let i=0;i<60;i++) ctrl.wheel(-100, {x:800,y:150});
  assert.equal(ctrl.targetZoom, 2);
  assert.equal(c.zoom, 1);
  for (let i=0;i<60;i++) {
    const previous=c.zoom; ctrl.update(1000/60);
    assert.ok(c.zoom >= previous && c.zoom <= 2);
  }
  assert.equal(c.zoom, 2);
  for (let i=0;i<100;i++) { ctrl.step(-1); ctrl.step(1); }
  ctrl.zoomTo(-100);
  for (let i=0;i<120;i++) ctrl.update(1000/60);
  assert.equal(c.zoom, 0.25);
});
test('wheel anchor preserves the exact world point through every interpolated frame', () => {
  const { camera: c, controller: ctrl } = setup();
  const before = worldAt(c, 800, 150);
  ctrl.wheel(-150, {x:800,y:150});
  for (let i=0;i<40;i++) {
    ctrl.update(16);
    const after = worldAt(c,800,150);
    assert.ok(Math.abs(after.x-before.x)<1e-9 && Math.abs(after.y-before.y)<1e-9);
  }
});
test('damping is independent of frame rate and zoom buttons retain viewport center', () => {
  const run = (fps: number) => {
    const {camera:c,controller:ctrl}=setup(); ctrl.step(1);
    for(let i=0;i<fps/2;i++) ctrl.update(1000/fps);
    assert.equal(c.scrollX,500); assert.equal(c.scrollY,500);
    return c.zoom;
  };
  assert.ok(Math.abs(run(30)-run(120))<1e-10);
});
test('reset animates zoom and position; dragging cancels focus without fighting the drag', () => {
  const {camera:c,controller:ctrl}=setup();
  ctrl.moveTo(1800,1400,0.5);
  assert.equal(c.scrollX,500); assert.equal(c.zoom,1);
  ctrl.update(16);
  assert.ok(c.zoom<1 && c.zoom>0.5 && c.scrollX>500 && c.scrollX<1300);
  ctrl.cancelPan(); c.scrollX=700;
  ctrl.update(16); assert.equal(c.scrollX,700);
  ctrl.moveTo(500,300,1,true);
  assert.equal(c.zoom,1); assert.equal(c.scrollX,0); assert.equal(c.scrollY,0);
  ctrl.destroy(); assert.equal(ctrl.targetZoom,c.zoom);
});
