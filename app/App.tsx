import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import {
  hasChosenTeam,
  hasSession,
  setOnSessionEnded,
} from './src/auth/session';
import { RootNavigator } from './src/navigation/RootNavigator';
import { colors } from './src/ui/parts';

type Stage = 'loading' | 'out' | 'needsTeam' | 'in';

function App() {
  const [stage, setStage] = useState<Stage>('loading');
  useEffect(() => {
    // A failed refresh (including refresh-token reuse) ends the session from inside the API client.
    setOnSessionEnded(() => setStage('out'));
    (async () => {
      if (!(await hasSession())) {
        return setStage('out');
      }
      setStage((await hasChosenTeam()) ? 'in' : 'needsTeam');
    })().catch(() => setStage('out'));
    return () => setOnSessionEnded(undefined);
  }, []);

  if (stage === 'loading') {
    return (
      <View
        style={styles.loading}
      >
        <ActivityIndicator accessibilityLabel="Loading" color={colors.accent} />
      </View>
    );
  }
  return (
    <SafeAreaProvider>
      <RootNavigator
        isSignedIn={stage === 'in'}
        needsTeam={stage === 'needsTeam'}
        onSignedIn={() => setStage('in')}
        onDevSkipSignIn={() => setStage('in')}
      />
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, justifyContent: 'center', backgroundColor: colors.paper },
});

export default App;
