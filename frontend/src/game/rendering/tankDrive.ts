import type Phaser from "phaser";
import { upgradeLevel } from "../upgradeLevel";
import { turretFrame } from "../systems/turretAim";
import { tankMovementYaw, TANK_REST_YAW, turnTank } from "../systems/tankDrive";
import { bakeTurretTextures, vehicleHullTexture } from "./aimedTurret";

/** Independent chassis yaw; only the sprite frame changes, never the hitbox/root. */
export class TankDrive {
  yaw = TANK_REST_YAW;
  desiredYaw = TANK_REST_YAW;
  private previous: {x: number; y: number};

  constructor(private root: Phaser.GameObjects.Container, private sprite: Phaser.GameObjects.Sprite,
    level: number, private size = 68, private kind: "tank" | "artillery" = "tank") {
    this.previous = {x: root.x, y: root.y};
    this.setLevel(level);
  }

  setLevel(level: number) {
    bakeTurretTextures(this.root.scene, this.kind, upgradeLevel(level), "hull");
    const height = this.kind === "artillery" ? .875 : .75;
    this.sprite.setTexture(vehicleHullTexture(level, this.kind), turretFrame(this.yaw))
      .setFlipX(false).setRotation(0).setOrigin(.5, (.89 - .25) / height)
      .setDisplaySize(this.size, this.size * height);
  }

  update(delta: number, active = true) {
    const next = {x: this.root.x, y: this.root.y};
    if (active) {
      const heading = tankMovementYaw(this.previous, next);
      if (heading !== null) { this.desiredYaw = heading; this.previous = next; }
      this.yaw = turnTank(this.yaw, this.desiredYaw, delta);
    } else this.previous = next;
    this.sprite.setFrame(turretFrame(this.yaw)).setFlipX(false).setRotation(0);
  }
}
