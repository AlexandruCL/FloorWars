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
      }),
    ),
    saveTrace: jest.fn(() =>
      Promise.resolve('/data/files/traces/stairs_up_pocket.csv'),
    ),
    onStatusChange: jest.fn(() => ({ remove: jest.fn() })),
  },
}));
