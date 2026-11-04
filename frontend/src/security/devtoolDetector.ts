import DisableDevtool from 'disable-devtool';

type DevtoolLibrary = typeof DisableDevtool;

export function installDevtoolDetector(onOpen: () => void, library: DevtoolLibrary = DisableDevtool): void {
  const detector = library.DetectorType;
  library({
    detectors: [
      detector.RegToString,
      detector.DefineId,
      detector.DateToString,
      detector.FuncToString,
      detector.Performance,
      detector.DebugLib,
    ],
    // Size caused false positives with sidebars/zoom. Debugger pauses gameplay.
    // Keep keyboard/context-menu handling in browserGuard to preserve controls.
    disableMenu: false,
    disableIframeParents: false,
    disableSelect: false,
    disableInputSelect: false,
    disableCopy: false,
    disableCut: false,
    disablePaste: false,
    clearLog: false,
    interval: 1000,
    clearIntervalWhenDevOpenTrigger: true,
    ondevtoolopen: () => onOpen(),
  });
}
