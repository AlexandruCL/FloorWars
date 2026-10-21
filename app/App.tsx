import { SafeAreaProvider } from 'react-native-safe-area-context';
import { RootNavigator } from './src/navigation/RootNavigator';

function App() {
  return (
    <SafeAreaProvider>
      <RootNavigator isSignedIn={false} />
    </SafeAreaProvider>
  );
}

export default App;
