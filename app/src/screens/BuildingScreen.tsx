import { StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '../api/client';
import { useMe } from '../data/myTeam';
import { clock, pullToRefresh, ReadState, useRead } from '../data/useRead';
import { useActiveCheckin } from '../checkin/active';
import type { MainStackParamList } from '../navigation/types';
import { useGameEvents } from '../realtime/useGameEvents';
import { BuildingDrawing } from '../standings/BuildingDrawing';
import { standingsOrder } from '../standings/facade';
import { fightLine } from '../standings/fight';
import { Body, Button, colors, Screen, TeamTag, type } from '../ui/parts';
import { minutesLeftMs } from './homeStatus';

type Props = NativeStackScreenProps<MainStackParamList, 'Building'>;

// "Tuesday 14:02" within the last week, "12 November" before that.
function sinceText(iso: string, now = Date.now()): string {
  const at = Date.parse(iso);
  return now - at < 6 * 24 * 3600 * 1000
    ? `${new Date(at).toLocaleDateString('en-GB', { weekday: 'long' })} ${clock(
        at,
      )}`
    : new Date(at).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'long',
      });
}

// One building: the drawing, who holds it, every team's points and what it takes to win it
// (DESIGN.md section 10).
export function BuildingScreen({ route, navigation }: Props) {
  // A deep link delivers the param as a string.
  const id = Number(route.params.buildingId);
  const standings = useRead(`standings:${id}`, () =>
    api('get', '/buildings/{id}/standings', { path: { id } }),
  );
  const buildings = useRead('buildings', () => api('get', '/buildings'));
  const name = buildings.data?.find(b => b.id === id)?.name ?? `Building ${id}`;
  const mine = useMe().data?.team?.code ?? null;
  const here = useActiveCheckin(navigation);
  const { width } = useWindowDimensions();
  const { bottom } = useSafeAreaInsets();

  // A flip here changes the owner and the order: read the standings again.
  const refetch = standings.refresh;
  useGameEvents(e => {
    if (e.type === 'building_flipped' && e.building_id === id) {
      refetch();
    }
  });

  const data = standings.data;
  const owner = data?.owner?.code ?? null;
  const teams = data ? standingsOrder(data.teams, owner) : [];
  const total = teams.reduce((s, t) => s + t.points, 0);
  const leader = teams[0]?.points ?? 0;

  return (
    <View style={styles.fill}>
      <Screen refreshControl={pullToRefresh(standings)}>
        <BuildingDrawing
          buildingId={id}
          teams={teams}
          owner={owner}
          name={name}
          width={width - 32}
          height={240}
        />
        <View style={styles.titleBlock}>
          <Text style={type.title} accessibilityRole="header">
            {name}
          </Text>
          {data && (
            <Text style={styles.sub}>
              {owner && data.claimed_at
                ? `Owned by ${owner} since ${sinceText(data.claimed_at)}`
                : owner
                ? `Owned by ${owner}`
                : 'Nobody owns it yet'}
            </Text>
          )}
        </View>
        <ReadState
          read={standings}
          notFoundText="This building doesn't exist anymore."
        />
        {data && <Body>{fightLine(teams, owner, mine)}</Body>}
        {teams.length > 0 && (
          <View accessibilityLabel="Standings, last 7 days">
            <View style={[styles.row, styles.headRow]}>
              <Text style={[styles.head, styles.teamCol]}>Team</Text>
              <Text style={[styles.head, styles.num, styles.pointsCol]}>
                Points
              </Text>
              <Text style={[styles.head, styles.num, styles.shareCol]}>
                Share
              </Text>
              <Text style={[styles.head, styles.num, styles.takeCol]}>
                To take it
              </Text>
            </View>
            {teams.map((t, i) => {
              const share = Math.round((t.points / total) * 100);
              const take =
                t.code === owner
                  ? 'Holds it'
                  : !owner && i === 0
                  ? 'Leads'
                  : (leader - t.points + 1).toLocaleString('en-US');
              const yours = t.code === mine;
              return (
                <View
                  key={t.code}
                  style={[styles.row, styles.bodyRow, yours && styles.yours]}
                  accessible
                  accessibilityLabel={`${t.code}${
                    yours ? ', your team' : ''
                  }: ${t.points} points, ${share} percent, ${
                    take === 'Holds it' || take === 'Leads'
                      ? take.toLowerCase()
                      : `needs ${take} to take it`
                  }`}
                >
                  <View style={[styles.teamCol, styles.team]}>
                    <TeamTag code={t.code} color={t.color_hex} />
                    {yours && <Text style={styles.sub}>Your team</Text>}
                  </View>
                  <Text style={[styles.figure, styles.num, styles.pointsCol]}>
                    {t.points.toLocaleString('en-US')}
                  </Text>
                  <Text
                    style={[
                      styles.figure,
                      styles.num,
                      styles.shareCol,
                      styles.dim,
                    ]}
                  >
                    {`${share}%`}
                  </Text>
                  <Text
                    style={[
                      t.code === owner || take === 'Leads'
                        ? styles.head
                        : styles.figure,
                      styles.num,
                      styles.takeCol,
                    ]}
                  >
                    {take}
                  </Text>
                </View>
              );
            })}
          </View>
        )}
        {data && (
          <Text style={styles.head}>
            Points from verified climbs in the last 7 days. The team with the
            most points owns the building.
          </Text>
        )}
      </Screen>
      {/* Sticky action bar: the one primary action on this screen. */}
      <View style={[styles.bar, { paddingBottom: 16 + bottom }]}>
        {here?.building_id === id ? (
          <Text style={[type.label, styles.center]}>
            {`You're climbing here, ${minutesLeftMs(
              here,
              Date.now(),
            )} min left`}
          </Text>
        ) : (
          <Button
            title="Check in here"
            wide
            onPress={() => navigation.navigate('Checkin')}
          />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.night },
  titleBlock: { gap: 6 },
  sub: { ...type.meta, color: colors.chalkDim },
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 8 },
  headRow: { paddingBottom: 6, alignItems: 'flex-end' },
  bodyRow: {
    minHeight: 48,
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
  },
  yours: { backgroundColor: colors.sunken, borderRadius: 8 },
  head: type.meta,
  figure: { ...type.label, fontVariant: ['tabular-nums'] },
  dim: { color: colors.chalkDim },
  num: { textAlign: 'right' },
  teamCol: { flex: 1 },
  team: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  pointsCol: { width: 64 },
  shareCol: { width: 52 },
  takeCol: { width: 84 },
  bar: {
    paddingTop: 12,
    paddingHorizontal: 16,
    backgroundColor: colors.raised,
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
  },
  center: { textAlign: 'center', paddingVertical: 13 },
});
