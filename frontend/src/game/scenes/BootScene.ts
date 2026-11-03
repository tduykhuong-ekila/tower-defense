import Phaser from "phaser";
import { MAX_UPGRADE_LEVEL } from "../upgradeLevel";
import { entityArtwork, infantryRunAnimation, infantryRunTexture, infantryTexture } from "../entityArtwork";
import { bakeTurretTextures } from "../rendering/aimedTurret";
export class BootScene extends Phaser.Scene {
  constructor() {
    super("BootScene");
  }
  preload() {
    const path = "/assets/woodland/";
    for (let i = 0; i < 20; i++) {
      this.load.svg(`base-${i}`, `${path}base-${i}.svg`);
      this.load.svg(`banner-${i}`, `${path}banner-${i}.svg`);
    }
    [
      "tree-0",
      "tree-1",
      "tree-2",
      "rock",
      "bush",
      "crate",
      "camp",
    ].forEach((key) => this.load.svg(key, `${path}${key}.svg`));
    for (let level = 1; level <= MAX_UPGRADE_LEVEL; level++) {
      const suffix = level > 1 ? `-lv${level}` : "";
      this.load.image(infantryTexture(level), entityArtwork("infantry", 0, level)!);
      this.load.spritesheet(infantryRunTexture(level), `${path}infantry-run-lv${level}.png`, {
        frameWidth: 512,
        frameHeight: 512,
      });
      for (const code of ["mg_tower", "cannon_tower", "tank", "artillery", "shield_generator"])
        this.load.image(`${code}${suffix}`, entityArtwork(code, 0, level)!);
      this.load.image(`cannon_tower-base${suffix}`, `${path}cannon_tower-base${suffix}.png`);
    }
    this.load.on("loaderror", () => this.game.events.emit("art-error"));
  }
  create() {
    bakeTurretTextures(this, "machineGun");
    for (let level = 1; level <= MAX_UPGRADE_LEVEL; level++) {
      this.anims.create({
        key: infantryRunAnimation(level),
        frames: this.anims.generateFrameNumbers(infantryRunTexture(level), { start: 0, end: 3 }),
        frameRate: 8,
        repeat: -1,
      });
    }
    this.scene.start("BattleScene");
  }
}
