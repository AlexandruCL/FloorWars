module.exports = {
  presets: ['module:@react-native/babel-preset'],
  // Reanimated 4 needs the worklets plugin, and it must be last.
  plugins: ['react-native-worklets/plugin'],
};
