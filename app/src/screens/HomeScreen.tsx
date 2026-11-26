import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AppState,
  Platform,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import type { CompositeScreenProps } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { api } from '../api/client';
import { seasonText, useMe } from '../data/myTeam';
import { clock, useRead } from '../data/useRead';
import { localMidnight, todayFigures } from '../history/today';
import {
  FLOOR_EQUIVALENT_LABEL,
  floorEquivalent,
} from '../scoring/floorEquivalent';
import { BuildingDrawing, type Replay } from '../standings/BuildingDrawing';
import { standingsOrder } from '../standings/facade';
import { fightLine } from '../standings/fight';
import { hasBarometer } from '../landing/landingScan';
import { FloorSensors } from '../native/floorSensors';
import type {
  ActiveCheckin,
  FloorSensorsStatus,
} from '../native/NativeFloorSensors';
import type { MainStackParamList, TabParamList } from '../navigation/types';
import {
  getSyncState,
  subscribeSync,
  syncNow,
  type SyncState,
} from '../sync/syncWorker';
import { Pictogram } from '../ui/Pictogram';
import {
  Body,
  Button,
  colors,
  fonts,
  Notice,
  Screen,
  TeamTag,
  type,
} from '../ui/parts';
import {
  minutesLeftMs,
  problemKind,
  problemText,
  showBatteryHint,
} from './homeStatus';

// Each native read can fail on its own; null means unknown and is shown as such.
type Snapshot = {
  status: FloorSensorsStatus | null;
  checkin: ActiveCheckin | null | undefined; // undefined: unknown, null: none
  pending: number | null;
  ignoringBattery: boolean | null;
};
const TICK_MS = 30_000;

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

type Nav = Props['navigation'];

// Today: the stencil numeral is the one hero number on this screen. Tap opens the history.
function Today({ onPress }: { onPress: () => void }) {
  const midnight = localMidnight(Date.now());
  const today = useRead(`today:${midnight}`, () => todayFigures(midnight));
  const f = today.data;
  if (!f) {
    return today.failure ? (
      <Text style={styles.meta}>
        {"Today's climbs can't be loaded right now."}
      </Text>
    ) : null;
  }
  const floors = floorEquivalent(f.steps);
  const detail = `${f.steps.toLocaleString(
    'en-US',
  )} verified steps, ${f.metres.toFixed(1)} m up`;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Today: ${floors} ${FLOOR_EQUIVALENT_LABEL}, ${detail}. Open climb history.`}
      onPress={onPress}
      style={styles.today}
    >
      <Text style={type.display}>{floors}</Text>
      <View style={styles.todayText}>
        <Text style={type.label}>{`${FLOOR_EQUIVALENT_LABEL} today`}</Text>
        <Text style={styles.sub}>{detail}</Text>
        {today.failure && today.cachedAt !== null && (
          <Text style={styles.meta}>
            {`Last updated ${clock(today.cachedAt)}. Can't reach the server.`}
          </Text>
        )}
      </View>
    </Pressable>
  );
}

// Your building drawn large, who holds it, and the top three teams over the last 7 days.
function YourBuilding({
  checkin,
  mine,
  navigation,
  replay,
}: {
  checkin: ActiveCheckin;
  mine: string | null;
  navigation: Nav;
  replay: Replay | null;
}) {
  const id = checkin.building_id;
  const { width } = useWindowDimensions();
  const standings = useRead(`standings:${id}`, () =>
    api('get', '/buildings/{id}/standings', { path: { id } }),
  );
  const buildings = useRead('buildings', () => api('get', '/buildings'));
  const name =
    buildings.data?.find(b => b.id === id)?.name ??
    checkin.building_name ??
    `Building ${id}`;
  const data = standings.data;
  const owner = data?.owner?.code ?? null;
  const teams = data ? standingsOrder(data.teams, owner) : [];
  const total = teams.reduce((s, t) => s + t.points, 0);
  const share = (points: number) => Math.round((points / total) * 100);
  return (
    <>
      <BuildingDrawing
        buildingId={id}
        teams={teams}
        owner={owner}
        name={name}
        width={width - 32}
        height={200}
        replay={replay}
      />
      <Text style={styles.name} accessibilityRole="header">
        {name}
      </Text>
      {data ? (
        <Body>{fightLine(teams, owner, mine)}</Body>
      ) : standings.failure ? (
        <Text style={styles.meta}>
          {"Standings can't be loaded right now. Pull down to try again."}
        </Text>
      ) : null}
      {teams.length > 0 && (
        <View>
          <View style={styles.sectionHead}>
            <Text style={styles.meta}>Last 7 days</Text>
            <Button
              title="All standings"
              variant="text"
              onPress={() =>
                navigation.navigate('Building', { buildingId: id })
              }
            />
          </View>
          {teams.slice(0, 3).map(t => (
            <View
              key={t.code}
              style={styles.standing}
              accessible
              accessibilityLabel={`${t.code}: ${t.points} points, ${share(
                t.points,
              )} percent`}
            >
              <TeamTag code={t.code} color={t.color_hex} />
              <Text style={[styles.figure, styles.grow]}>
                {t.points.toLocaleString('en-US')}
                <Text style={styles.unit}> points</Text>
              </Text>
              <Text style={[styles.figure, styles.dim]}>
                {`${share(t.points)}%`}
              </Text>
            </View>
          ))}
        </View>
      )}
    </>
  );
}

function NotCheckedIn({ navigation }: { navigation: Nav }) {
  const { width } = useWindowDimensions();
  return (
    <>
      <BuildingDrawing
        buildingId={16}
        teams={[]}
        owner={null}
        unlit
        name="Not checked in"
        width={width - 32}
        height={180}
      />
      <Text style={styles.name} accessibilityRole="header">
        Pick a building to climb for
      </Text>
      <Body>
        Your climbs count for the building you check in to, for 90 minutes.
      </Body>
      <View style={styles.actions}>
        <Button
          title="Pick a building"
          onPress={() => navigation.navigate('Buildings')}
        />
        <Pressable
          accessibilityRole="button"
          onPress={() => navigation.navigate('Checkin')}
          style={styles.scan}
        >
          <Pictogram name="scan" size={20} color={colors.chalk} />
          <Text style={type.label}>Scan entrance code</Text>
        </Pressable>
      </View>
    </>
  );
}

type Props = CompositeScreenProps<
  BottomTabScreenProps<TabParamList, 'Climb'>,
  NativeStackScreenProps<MainStackParamList>
>;

type NoticeProps = Parameters<typeof Notice>[0];

// The Climb tab: do my climbs count, and are we winning my building? (DESIGN.md section 10)
export function HomeScreen({ navigation }: Props) {
  const { snap, now, refresh } = useSnapshot();
  const sync = useSync();
  const me = useMe();

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

  const team = me.data?.team ?? null;
  const problem = problemKind(sync);
  const noBarometer = snap !== null && !hasBarometer(snap.status);
  // Every native read failed: nothing on this screen can be trusted.
  const unreadable =
    snap !== null &&
    snap.status === null &&
    snap.checkin === undefined &&
    snap.pending === null;
  const checkin =
    snap?.checkin && minutesLeftMs(snap.checkin, now) > 0 ? snap.checkin : null;

  // A new check-in lights the windows from the ground up; the first read after opening only
  // records the current one, so a launch does not replay it (DESIGN.md section 11).
  const seenCheckin = useRef<string | null | undefined>(undefined);
  const [lightUp, setLightUp] = useState<Replay | null>(null);
  const checkinId = snap ? checkin?.checkin_id ?? null : undefined;
  useEffect(() => {
    if (checkinId === undefined) {
      return;
    }
    if (
      seenCheckin.current !== undefined &&
      checkinId &&
      checkinId !== seenCheckin.current
    ) {
      setLightUp({ kind: 'checkin', from: [], owner: null, key: Date.now() });
    }
    seenCheckin.current = checkinId;
  }, [checkinId]);

  // Status speaks only when something needs the player, most urgent first, at most two.
  const notices: NoticeProps[] = [];
  if (snap && !unreadable) {
    if (noBarometer) {
      notices.push({
        message:
          "This phone can't measure height. Scan the sticker on a stair landing after you climb.",
        action: {
          title: 'Scan stair sticker',
          onPress: () => navigation.navigate('LandingScan'),
        },
      });
    } else if (checkin && snap.status && !snap.status.detecting) {
      notices.push({
        message: 'Detection is off, so climbs are not recorded.',
      });
    }
    if (showBatteryHint(Platform.OS, snap.ignoringBattery)) {
      notices.push({
        message:
          'Battery saver can stop climb detection while the screen is off.',
        action: {
          title: 'Open battery settings',
          onPress: () => FloorSensors.openBatteryOptimizationSettings(),
        },
      });
    }
    if (problem) {
      const retry = problem === 'offline' || problem === 'error';
      notices.push({
        kind: problem === 'stuck' ? 'bad' : 'warn',
        message: problemText(problem, sync),
        action: retry ? { title: 'Upload now', onPress: syncNow } : undefined,
      });
    }
  }

  const pending = snap?.pending ?? 0;
  const detecting = !!snap?.status?.detecting;
  const statusLine = [
    noBarometer ? null : detecting ? 'Detection on.' : 'Detection off.',
    sync.last ? `Last upload ${clock(sync.last.at)}.` : null,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <Screen
      refreshControl={
        <RefreshControl
          refreshing={sync.running}
          onRefresh={() => {
            // Pull to refresh also uploads (DESIGN.md section 3).
            syncNow();
            refresh();
            me.refresh();
          }}
        />
      }
    >
      {team && me.data && (
        <View style={styles.top}>
          <TeamTag code={team.code} color={team.color_hex} />
          <Text style={styles.sub}>{seasonText(me.data.season)}</Text>
        </View>
      )}
      {snap === null ? (
        <View accessibilityLabel="Loading" style={styles.loading} />
      ) : unreadable ? (
        <Notice
          kind="bad"
          message="Couldn't read the sensor service. Close and reopen the app."
          action={{ title: 'Try again', onPress: refresh }}
        />
      ) : (
        <>
          {notices.slice(0, 2).map(n => (
            <Notice key={n.message} {...n} />
          ))}
          {checkin ? (
            <>
              <YourBuilding
                checkin={checkin}
                mine={team?.code ?? null}
                navigation={navigation}
                replay={lightUp}
              />
              <View style={styles.checkin}>
                <View style={styles.grow}>
                  <Text style={type.label}>Checked in</Text>
                  <Text style={styles.sub}>
                    {`${minutesLeftMs(checkin, now)} min left`}
                  </Text>
                </View>
                <Button
                  title="Switch building"
                  variant="text"
                  onPress={() => navigation.navigate('Buildings')}
                />
              </View>
            </>
          ) : (
            <NotCheckedIn navigation={navigation} />
          )}
          <Today onPress={() => navigation.navigate('History')} />
          {pending > 0 && !problem ? (
            <View style={styles.waiting}>
              <Text style={styles.meta}>
                {`${pending} ${
                  pending === 1 ? 'climb' : 'climbs'
                } waiting to upload.`}
              </Text>
              <Button
                title="Upload now"
                variant="text"
                busy={sync.running}
                onPress={syncNow}
              />
            </View>
          ) : statusLine ? (
            <View style={styles.statusLine}>
              {detecting && <View style={styles.dot} />}
              <Text style={styles.meta}>{statusLine}</Text>
            </View>
          ) : null}
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  top: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 44 },
  loading: { height: 200 },
  name: { ...type.title, fontSize: 30, lineHeight: 32, marginBottom: -8 },
  sectionHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  standing: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    minHeight: 44,
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
  },
  figure: { ...type.label, fontVariant: ['tabular-nums'] },
  unit: { fontFamily: fonts.medium, fontSize: 13, color: colors.chalkFaint },
  dim: { color: colors.chalkDim },
  grow: { flex: 1 },
  checkin: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 4,
    paddingLeft: 16,
    paddingRight: 4,
    borderRadius: 12,
    backgroundColor: colors.raised,
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 12,
  },
  scan: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minHeight: 48,
    paddingHorizontal: 12,
  },
  today: { flexDirection: 'row', alignItems: 'flex-end', gap: 14 },
  todayText: { paddingBottom: 2, flexShrink: 1 },
  sub: { ...type.meta, color: colors.chalkDim },
  meta: type.meta,
  waiting: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap' },
  statusLine: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.ok },
});
