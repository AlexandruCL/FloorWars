import { useState } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { signInWithStub } from './src/auth/authStub';
import { RootNavigator } from './src/navigation/RootNavigator';

function App() {
  const [isSignedIn, setSignedIn] = useState(false);
  return (
    <SafeAreaProvider>
      <RootNavigator
        isSignedIn={isSignedIn}
        onStubSignIn={() => signInWithStub(() => setSignedIn(true))}
        onDevSkipSignIn={() => setSignedIn(true)}
      />
    </SafeAreaProvider>
  );
}

export default App;
