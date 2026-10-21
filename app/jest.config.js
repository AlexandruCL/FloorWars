module.exports = {
  preset: '@react-native/jest-preset',
  setupFiles: ['./jest.setup.js'],
  // Typed contract samples, checked by apiContract.typecheck.test.js; not a test file.
  testPathIgnorePatterns: ['/node_modules/', '<rootDir>/__tests__/contract/'],
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community)?|@react-navigation)/)',
  ],
};
