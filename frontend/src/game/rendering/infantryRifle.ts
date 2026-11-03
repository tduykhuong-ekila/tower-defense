import type Phaser from "phaser";
import { infantryTexture } from "../entityArtwork";

/** Recoil affects only the artwork; movement remains server authoritative. */
export class InfantryRifle {
  private elapsed = 0;
  private direction = 1;
  private readonly flash: Phaser.GameObjects.Graphics;
  public attacking = false;

  constructor(private root: Phaser.GameObjects.Container, private sprite: Phaser.GameObjects.Sprite) {
    this.flash = root.scene.add.graphics().setVisible(false);
    this.flash.fillStyle(0xffdf88).fillPoints([
      { x: 0, y: -2 }, { x: 9, y: -6 }, { x: 6, y: 0 },
      { x: 12, y: 3 }, { x: 0, y: 3 },
    ], true);
    root.add(this.flash);
  }

  fire(_team: number, level: number, target: { x: number; y: number }) {
    this.cancel();
    this.elapsed = 0;
    this.attacking = true;
    this.direction = target.x < this.root.x ? -1 : 1;
    this.sprite.stop().setFlipX(this.direction < 0);
    this.sprite.setTexture(infantryTexture(level));
    const muzzle = this.muzzle();
    this.flash.setPosition(muzzle.x - this.root.x, muzzle.y - this.root.y)
      .setScale(this.direction, 1).setVisible(this.root.visible);
  }

  muzzle() {
    return {
      x: this.root.x + this.sprite.x + this.direction * this.sprite.displayWidth * 29 / 64,
      y: this.root.y + this.sprite.y + this.sprite.displayHeight * (37 / 64 - this.sprite.originY),
    };
  }

  update(delta: number, active: boolean, _team: number, _level: number) {
    if (!this.attacking) return;
    this.elapsed += delta;
    if (!active || this.elapsed >= 180) { this.cancel(); return; }
    this.sprite.x = -this.direction * 3 * (1 - this.elapsed / 180);
    this.flash.setVisible(this.root.visible && this.elapsed < 65);
  }

  cancel() {
    this.attacking = false;
    this.sprite.x = 0;
    this.flash.setVisible(false);
  }
}
