/* eslint-env jest */
jest.mock(
  'react-native-safe-area-context',
  () => require('react-native-safe-area-context/jest/mock').default,
);

jest.mock('react-native-keychain', () => {
  const store = {};
  return {
    setGenericPassword: jest.fn(async (username, password, options = {}) => {
      store[options.service ?? ''] = { username, password };
      return { service: options.service, storage: 'mock' };
    }),
    getGenericPassword: jest.fn(
      async (options = {}) => store[options.service ?? ''] ?? false,
    ),
    resetGenericPassword: jest.fn(async (options = {}) => {
      delete store[options.service ?? ''];
      return true;
    }),
  };
});

jest.mock('react-native-share', () => ({
  __esModule: true,
  default: { open: jest.fn(() => Promise.resolve({ success: true })) },
}));

jest.mock('./src/native/NativeFloorSensors', () => ({
  __esModule: true,
  default: {
    startLogging: jest.fn(),
    stopLogging: jest.fn(),
    getStatus: jest.fn(() =>
      Promise.resolve({
        logging: false,
        label: '',
        has_barometer: true,
        buffered: 0,
        detecting: false,
        last_segment_ms: null,
        rejected_count: 0,
        no_checkin_count: 0,
        longest_gap_s: 0,
        gaps_over_threshold: 0,
      }),
    ),
    saveTrace: jest.fn(() =>
      Promise.resolve('/data/files/traces/stairs_up_pocket.csv'),
    ),
    onStatusChange: jest.fn(() => ({ remove: jest.fn() })),
    setActiveCheckin: jest.fn(),
    clearActiveCheckin: jest.fn(),
    getActiveCheckin: jest.fn(() => Promise.resolve(null)),
    onPendingChanged: jest.fn(() => ({ remove: jest.fn() })),
    getPending: jest.fn(() => Promise.resolve([])),
    markSynced: jest.fn(() => Promise.resolve()),
    markRejected: jest.fn(() => Promise.resolve()),
    getPendingCount: jest.fn(() => Promise.resolve(0)),
    clearPending: jest.fn(() => Promise.resolve()),
    isIgnoringBatteryOptimizations: jest.fn(() => Promise.resolve(true)),
    openBatteryOptimizationSettings: jest.fn(),
  },
}));

// Native camera and location modules don't load under Jest; tests inject their own CheckinDeps.
jest.mock('react-native-vision-camera', () => ({
  VisionCamera: { requestCameraPermission: jest.fn(async () => true) },
  useCameraDevice: jest.fn(() => undefined),
  Camera: () =>
    require('react').createElement(require('react-native').View, {
      testID: 'camera',
    }),
}));
jest.mock('react-native-vision-camera-barcode-scanner', () => ({
  useBarcodeScannerOutput: jest.fn(() => ({})),
}));
jest.mock('@react-native-community/geolocation', () => ({
  __esModule: true,
  default: { getCurrentPosition: jest.fn() },
}));
