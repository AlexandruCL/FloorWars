import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  AppState,
  Platform,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { clock, useRead } from '../data/useRead';
import { localMidnight, todayFigures, todayText } from '../history/today';
import { revokeRefreshToken } from '../auth/logout';
import { endSession } from '../auth/session';
import { hasBarometer } from '../landing/landingScan';
import { FloorSensors } from '../native/floorSensors';
import type {
  ActiveCheckin,
  FloorSensorsStatus,
} from '../native/NativeFloorSensors';
import type { MainStackParamList } from '../navigation/types';
import {
  getSyncState,
  subscribeSync,
  syncNow,
  type SyncState,
} from '../sync/syncWorker';
import {
  Body,
  Button,
  colors,
  ErrorText,
  Heading,
  Screen,
  type,
} from '../ui/parts';
import {
  lastSyncText,
  minutesLeftMs,
  problemKind,
  problemText,
  showBatteryHint,
  timeText,
} from './homeStatus';

// Each native read can fail on its own; null means unknown and is shown as such.
type Snapshot = {
  status: FloorSensorsStatus | null;
  checkin: ActiveCheckin | null | undefined; // undefined: unknown, null: none
  pending: number | null;
  ignoringBattery: boolean | null;
};
const TICK_MS = 30_000;

async function confirmSignOut() {
  const n = await FloorSensors.getPendingCount().catch(() => 0);
  Alert.alert(
    'Sign out?',
    n > 0
      ? `${n} ${
          n === 1 ? 'segment is' : 'segments are'
        } not uploaded yet and will be deleted.`
      : 'You will need to sign in again.',
    [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Sign out',
        style: 'destructive',
        onPress: async () => {
          await revokeRefreshToken();
          await endSession();
        },
      },
    ],
  );
}

async function read(): Promise<Snapshot> {
  const [status, checkin, pending, battery] = await Promise.allSettled([
    FloorSensors.getStatus(),
    FloorSensors.getActiveCheckin(),
    FloorSensors.getPendingCount(),
    Platform.OS === 'android'
      ? FloorSensors.isIgnoringBatteryOptimizations()
      : Promise.resolve(true),
  ]);
  const value = <T,>(r: PromiseSettledResult<T>) =>
    r.status === 'fulfilled' ? r.value : null;
  return {
    status: value(status),
    checkin: checkin.status === 'fulfilled' ? checkin.value : undefined,
    pending: value(pending),
    ignoringBattery: value(battery),
  };
}

function useSnapshot() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [now, setNow] = useState(Date.now());
  const refresh = useCallback(async () => {
    setSnap(await read());
    setNow(Date.now());
  }, []);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, TICK_MS);
    // Back from the battery settings, or a new segment: read again.
    const app = AppState.addEventListener('change', s => {
      if (s === 'active') {
        refresh();
      }
    });
    const pending = FloorSensors.onPendingChanged(refresh);
    return () => {
      clearInterval(timer);
      app.remove();
      pending.remove();
    };
  }, [refresh]);
  return { snap, now, refresh };
}

function useSync(): SyncState {
  const [sync, setSync] = useState(getSyncState());
  useEffect(() => {
    setSync(getSyncState());
    return subscribeSync(() => setSync(getSyncState()));
  }, []);
  return sync;
}

// Today's figures: verified climbs since local midnight. The key holds the date, so a new day
// starts without a cached copy.
function TodayFigures() {
  const midnight = localMidnight(Date.now());
  const today = useRead(`today:${midnight}`, () => todayFigures(midnight));
  const stale = today.failure && today.data;
  const text =
    today.data && !today.failure
      ? todayText(today.data)
      : today.failure
      ? 'Verified today: unavailable'
      : 'Verified today: loading';
  return (
    <View style={styles.today}>
      <Text style={styles.value} accessibilityLiveRegion="polite">
        {text}
      </Text>
      {stale && today.data && today.cachedAt !== null && (
        <>
          <Text style={styles.label}>{todayText(today.data)}</Text>
          <Text style={styles.label}>
            {`Last updated ${clock(today.cachedAt)}. Can't reach the server.`}
          </Text>
        </>
      )}
    </View>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View
      style={styles.row}
      accessible
      accessibilityLabel={`${label}: ${value}`}
    >
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

export function HomeScreen({
  navigation,
}: NativeStackScreenProps<MainStackParamList, 'Home'>) {
  const { snap, now, refresh } = useSnapshot();
  const sync = useSync();

  // Coming back from the check-in screen: read again.
  useEffect(
    () => navigation.addListener('focus', refresh),
    [navigation, refresh],
  );
  // A finished sync changes the pending count.
  useEffect(() => {
    if (!sync.running) {
      refresh();
    }
  }, [sync.running, refresh]);

  const problem = problemKind(sync);
  const noBarometer = snap !== null && !hasBarometer(snap.status);
  // Every native read failed: nothing on this screen can be trusted.
  const unreadable =
    snap !== null &&
    snap.status === null &&
    snap.checkin === undefined &&
    snap.pending === null;

  const checkinText = (c: ActiveCheckin | null | undefined) => {
    if (c === undefined) {
      return 'Unknown';
    }
    if (c === null) {
      return 'None';
    }
    const left = minutesLeftMs(c, now);
    const where = c.building_name ?? 'Building';
    return left > 0 ? `${where}, ${left} min left` : `${where}, expired`;
  };

  return (
    <Screen>
      <Heading>Status</Heading>
      {snap === null ? (
        <Body>Loading status...</Body>
      ) : unreadable ? (
        <>
          <ErrorText message="Could not read the sensor service. Close and reopen the app." />
          <Button title="Try again" onPress={refresh} secondary />
        </>
      ) : (
        <>
          <View>
            {!noBarometer && (
              <Row
                label="Detection"
                value={
                  snap.status === null
                    ? 'Unknown'
                    : snap.status.detecting
                    ? 'Running'
                    : 'Not running'
                }
              />
            )}
            <Row label="Check-in" value={checkinText(snap.checkin)} />
            {!noBarometer && (
              <Row
                label="Last segment"
                value={
                  snap.status
                    ? timeText(snap.status.last_segment_ms)
                    : 'Unknown'
                }
              />
            )}
            <Row
              label="Waiting to upload"
              value={snap.pending === null ? 'Unknown' : String(snap.pending)}
            />
            <Row label="Last upload" value={lastSyncText(sync)} />
          </View>
          {snap.checkin === null && (
            <Body>
              No active check-in, so no climbs count. Check in at the building
              you are about to climb.
            </Body>
          )}
          {!noBarometer && snap.status !== null && !snap.status.detecting && (
            <Body>Detection is not running, so climbs are not recorded.</Body>
          )}
          {problem && <ErrorText message={problemText(problem, sync)} />}
          {showBatteryHint(Platform.OS, snap.ignoringBattery) && (
            <View style={styles.hint}>
              <Body>
                Battery saving can stop climb detection while the screen is off.
              </Body>
              <Button
                title="Open battery settings"
                secondary
                onPress={() => FloorSensors.openBatteryOptimizationSettings()}
              />
            </View>
          )}
        </>
      )}
      <TodayFigures />
      {/* Buttons stay reachable in every state. */}
      <Button title="Sync now" busy={sync.running} onPress={() => syncNow()} />
      <Button
        title="Check in"
        secondary
        onPress={() => navigation.navigate('Checkin')}
      />
      {noBarometer && (
        <Button
          title="Scan at the stairs"
          onPress={() => navigation.navigate('LandingScan')}
        />
      )}
      {snap?.checkin && (
        <Button
          title="Building standings"
          secondary
          onPress={() =>
            navigation.navigate('Standings', {
              buildingId: snap.checkin!.building_id,
            })
          }
        />
      )}
      <Button
        title="Leaderboards"
        secondary
        onPress={() => navigation.navigate('Leaderboards')}
      />
      <Button
        title="Climb history"
        secondary
        onPress={() => navigation.navigate('History')}
      />
      <Button
        title="How it works"
        secondary
        onPress={() => navigation.navigate('Onboarding')}
      />
      <Button
        title="Sensor logger"
        secondary
        onPress={() => navigation.navigate('SensorLogger')}
      />
      <Button title="Sign out" onPress={confirmSignOut} secondary />
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: {
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.hairline,
    gap: 2,
  },
  label: type.meta,
  value: { ...type.label, fontSize: 18 },
  hint: { gap: 12, marginTop: 8 },
  today: { gap: 2 },
});
