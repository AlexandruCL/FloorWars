import { useState } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { RootNavigator } from './src/navigation/RootNavigator';

function App() {
  const [isSignedIn, setSignedIn] = useState(false);
  return (
    <SafeAreaProvider>
      <RootNavigator
        isSignedIn={isSignedIn}
        onDevSkipSignIn={() => setSignedIn(true)}
      />
    </SafeAreaProvider>
  );
}

export default App;
