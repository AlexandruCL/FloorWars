import { useEffect, useState } from 'react';
import { ActivityIndicator, AppState, StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { api } from './src/api/client';
import {
  getChosenSeason,
  hasSession,
  setOnSessionEnded,
} from './src/auth/session';
import { startSyncTriggers } from './src/sync/triggers';
import { RootNavigator } from './src/navigation/RootNavigator';
import { colors } from './src/ui/parts';

type Stage = 'loading' | 'out' | 'needsTeam' | 'in';

// A new season starts with no memberships: show the team picker again when the running season
// is not the one the user joined. If the season cannot be read (offline, none running), stay in
// and check again on the next start.
async function stageForSession(): Promise<Stage> {
  const chosen = await getChosenSeason();
  if (chosen === null) {
    return 'needsTeam';
  }
  try {
    const season = await api('get', '/seasons/active');
    return season.id === chosen ? 'in' : 'needsTeam';
  } catch {
    return 'in';
  }
}

function App() {
  const [stage, setStage] = useState<Stage>('loading');
  useEffect(() => {
    // A failed refresh (including refresh-token reuse) ends the session from inside the API client.
    setOnSessionEnded(() => setStage('out'));
    (async () => {
      if (!(await hasSession())) {
        return setStage('out');
      }
      setStage(await stageForSession());
    })().catch(() => setStage('out'));
    return () => setOnSessionEnded(undefined);
  }, []);

  useEffect(() => (stage === 'in' ? startSyncTriggers() : undefined), [stage]);

  // A season can roll over while the app is open: look again each time it comes back.
  useEffect(() => {
    if (stage !== 'in') {
      return undefined;
    }
    const sub = AppState.addEventListener('change', status => {
      if (status !== 'active') {
        return;
      }
      (async () => {
        if ((await hasSession()) && (await stageForSession()) === 'needsTeam') {
          setStage('needsTeam');
        }
      })().catch(() => {});
    });
    return () => sub.remove();
  }, [stage]);

  if (stage === 'loading') {
    return (
      <View style={styles.loading}>
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
