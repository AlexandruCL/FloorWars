/* eslint-env jest */
jest.mock(
  'react-native-safe-area-context',
  () => require('react-native-safe-area-context/jest/mock').default,
);

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
    onStatusChange: jest.fn(() => ({ remove: jest.fn() })),
  },
}));
