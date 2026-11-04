import test from 'node:test';
import assert from 'node:assert/strict';
import DisableDevtool from 'disable-devtool';
import { installDevtoolDetector } from '../src/security/devtoolDetector';

test('disable-devtool uses console probes and timing without size detection, debugger or parent-frame blocking', () => {
  let config: Parameters<typeof DisableDevtool>[0];
  const library = Object.assign((options: typeof config) => {
    config = options;
    return { success: true, reason: '' };
  }, { DetectorType: DisableDevtool.DetectorType }) as typeof DisableDevtool;
  let opens = 0;
  installDevtoolDetector(() => { opens++; }, library);
  assert.ok(config);
  assert.deepEqual(config.detectors, [0, 1, 3, 4, 6, 7]);
  assert.equal(config.disableIframeParents, false);
  assert.equal(config.disableMenu, false);
  assert.equal(config.disableSelect, false);
  assert.equal(config.disableCopy, false);
  assert.equal(config.disablePaste, false);
  assert.equal(config.clearLog, false);
  assert.equal(config.clearIntervalWhenDevOpenTrigger, true);
  assert.equal(opens, 0);
  config.ondevtoolopen!(DisableDevtool.DetectorType.DefineId, () => assert.fail('must not close/redirect the window'));
  assert.equal(opens, 1);
});
