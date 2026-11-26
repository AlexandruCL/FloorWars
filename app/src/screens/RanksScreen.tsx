import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { CompositeScreenProps } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { api } from '../api/client';
import { useMe } from '../data/myTeam';
import { pullToRefresh, ReadState, useRead } from '../data/useRead';
import { FloorSensors } from '../native/floorSensors';
import type { MainStackParamList, TabParamList } from '../navigation/types';
import { teamTone } from '../ui/tone';
import { Pictogram } from '../ui/Pictogram';
import {
  Body,
  colors,
  fonts,
  Heading,
  Row,
  RowGroup,
  Screen,
  Segmented,
  Sheet,
  TeamTag,
  type,
} from '../ui/parts';

type Props = CompositeScreenProps<
  BottomTabScreenProps<TabParamList, 'Ranks'>,
  NativeStackScreenProps<MainStackParamList>
>;
type Scope = 'individual' | 'team' | 'building';
const SCOPES: { value: Scope; label: string }[] = [
  { value: 'individual', label: 'Players' },
  { value: 'team', label: 'Teams' },
  { value: 'building', label: 'In a building' },
];
const LIMIT = 50;

// GET /seasons may not be deployed yet (contract 0.8.0): then only the active season is offered.
export async function loadSeasons() {
  const active = await api('get', '/seasons/active');
  const all = await api('get', '/seasons').catch(() => []);
  return {
    activeId: active.id,
    ids: all.some(s => s.id === active.id)
      ? all.map(s => s.id)
      : [active.id, ...all.map(s => s.id)],
  };
}

// 1st, 2nd, 3rd, 4th, 11th, 12th, 13th, 21st.
export function ordinal(n: number): string {
  const teen = n % 100 >= 11 && n % 100 <= 13;
  const suffix = teen ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th';
  return `${n}${suffix}`;
}

// Players, Teams or one building's teams this season, your row marked (DESIGN.md section 10).
export function RanksScreen(_: Props) {
  const [scope, setScope] = useState<Scope>('individual');
  const [season, setSeason] = useState<number | null>(null);
  const [building, setBuilding] = useState<number | null>(null);

  const seasons = useRead('seasons', loadSeasons);
  const buildings = useRead('buildings', () => api('get', '/buildings'));
  const teams = useRead('teams', () => api('get', '/teams'));
  const me = useMe();

  const [picker, setPicker] = useState<'season' | 'building' | null>(null);

  useEffect(() => {
    if (season === null && seasons.data) {
      setSeason(seasons.data.activeId);
    }
  }, [season, seasons.data]);

  // Default building: the active check-in's, else the first by name.
  useEffect(() => {
    const list = buildings.data;
    if (building !== null || !list || list.length === 0) {
      return;
    }
    let live = true;
    FloorSensors.getActiveCheckin()
      .catch(() => null)
      .then(c => {
        const mine = list.find(b => b.id === c?.building_id);
        const first = [...list].sort((a, b) => a.name.localeCompare(b.name))[0];
        live && setBuilding((mine ?? first).id);
      });
    return () => {
      live = false;
    };
  }, [building, buildings.data]);

  const needsBuilding = scope === 'building';
  const ready = season !== null && (!needsBuilding || building !== null);
  const board = useRead(
    ready ? `board:${scope}:${season}:${needsBuilding ? building : ''}` : null,
    () =>
      api('get', '/leaderboards', {
        query: {
          scope,
          season_id: season ?? undefined,
          limit: LIMIT,
          building_id: needsBuilding ? building ?? undefined : undefined,
        },
      }),
  );
  // Your own rank in the chosen season, to mark or pin your row.
  const stats = useRead(season !== null ? `stats:${season}` : null, () =>
    api('get', '/me/season-stats', { query: { season_id: season! } }),
  );

  const myTeam = me.data?.team?.code ?? null;
  const colorOf = (code: string) =>
    teams.data?.find(t => t.code === code)?.color_hex ?? colors.chalkFaint;
  const entries = board.data?.entries ?? [];
  const top = Math.max(1, ...entries.map(e => e.points));
  const isMine = (e: (typeof entries)[number]) =>
    scope === 'individual'
      ? !!stats.data &&
        e.rank === stats.data.rank &&
        e.points === stats.data.points
      : e.id === myTeam;
  const pinned =
    scope === 'individual' &&
    board.data &&
    stats.data?.rank &&
    !entries.some(isMine)
      ? stats.data
      : null;
  const buildingName = buildings.data?.find(b => b.id === building)?.name;

  return (
    <View style={styles.fill}>
      <Screen refreshControl={pullToRefresh(board)}>
        <View style={styles.titleRow}>
          <Heading>Ranks</Heading>
          {season !== null && (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Season ${season}. Change season`}
              onPress={() => setPicker('season')}
              style={styles.seasonButton}
            >
              <Text style={type.label}>{`Season ${season}`}</Text>
              <Pictogram name="down" size={20} color={colors.chalk} />
            </Pressable>
          )}
        </View>
        <Segmented items={SCOPES} selected={scope} onSelect={setScope} />
        {needsBuilding && buildingName && (
          <View style={styles.select}>
            <Row
              title={buildingName}
              subline="Building"
              onPress={() => setPicker('building')}
            />
          </View>
        )}
        {!ready ? (
          needsBuilding && buildings.data?.length === 0 ? (
            <Body>No points on this board yet this season.</Body>
          ) : (
            <ReadState read={season === null ? seasons : buildings} />
          )
        ) : (
          <>
            <ReadState read={board} />
            {board.data && entries.length === 0 && (
              <Body>No points on this board yet this season.</Body>
            )}
            {entries.length > 0 && (
              <View>
                {entries.map(e => {
                  const mine = isMine(e);
                  const label = `${e.rank}. ${e.name}${
                    mine
                      ? scope === 'individual'
                        ? ', you'
                        : ', your team'
                      : ''
                  }, ${e.points.toLocaleString('en-US')} points`;
                  return scope === 'individual' ? (
                    <View
                      key={`${e.rank}:${e.id}`}
                      style={[styles.player, mine && styles.mine]}
                      accessible
                      accessibilityLabel={label}
                    >
                      <Text style={styles.playerRank}>{e.rank}</Text>
                      <Text style={[type.label, styles.grow]} numberOfLines={1}>
                        {e.name}
                      </Text>
                      {mine && <Text style={styles.you}>You</Text>}
                      <Text style={styles.figure}>
                        {e.points.toLocaleString('en-US')}
                      </Text>
                    </View>
                  ) : (
                    <View
                      key={`${e.rank}:${e.id}`}
                      style={[styles.team, mine && styles.mine]}
                      accessible
                      accessibilityLabel={label}
                    >
                      <View style={styles.teamLine}>
                        <Text style={[styles.teamRank, !mine && styles.dim]}>
                          {e.rank}
                        </Text>
                        <TeamTag
                          code={e.name}
                          color={colorOf(e.id)}
                          size="medium"
                        />
                        {mine && <Text style={styles.sub}>Your team</Text>}
                        <Text style={[styles.figure, styles.right]}>
                          {e.points.toLocaleString('en-US')}
                          <Text style={styles.unit}> points</Text>
                        </Text>
                      </View>
                      <View style={styles.barTrack}>
                        <View
                          style={[
                            styles.bar,
                            {
                              width: `${(e.points / top) * 100}%`,
                              backgroundColor: teamTone(colorOf(e.id)).tone,
                            },
                          ]}
                        />
                      </View>
                    </View>
                  );
                })}
              </View>
            )}
            {board.data && (
              <Text style={type.meta}>
                Season points from verified stair steps. Each hour, steps past
                the first 300 count half.
              </Text>
            )}
          </>
        )}
      </Screen>
      <Sheet
        visible={picker !== null}
        title={picker === 'building' ? 'Building' : 'Season'}
        onClose={() => setPicker(null)}
      >
        <RowGroup>
          {picker === 'season'
            ? (seasons.data?.ids ?? []).map(id => (
                <Row
                  key={id}
                  title={`Season ${id}`}
                  subline={
                    id === seasons.data?.activeId ? 'Running now' : undefined
                  }
                  value={id === season ? 'Selected' : undefined}
                  onPress={() => {
                    setSeason(id);
                    setPicker(null);
                  }}
                />
              ))
            : [...(buildings.data ?? [])]
                .sort((a, b) => a.name.localeCompare(b.name))
                .map(b => (
                  <Row
                    key={b.id}
                    title={b.name}
                    value={b.id === building ? 'Selected' : undefined}
                    onPress={() => {
                      setBuilding(b.id);
                      setPicker(null);
                    }}
                  />
                ))}
        </RowGroup>
      </Sheet>
      {pinned && (
        <View
          style={styles.pinned}
          accessible
          accessibilityLabel={`You, ${ordinal(pinned.rank!)}, ${
            pinned.points
          } points`}
        >
          <Text style={type.label}>{`You, ${ordinal(pinned.rank!)}`}</Text>
          <Text style={styles.figure}>
            {`${pinned.points.toLocaleString('en-US')} points`}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.night },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  seasonButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    minHeight: 48,
    paddingLeft: 12,
  },
  select: {
    backgroundColor: colors.raised,
    borderRadius: 12,
    overflow: 'hidden',
  },
  grow: { flex: 1 },
  dim: { color: colors.chalkDim },
  sub: { ...type.meta, color: colors.chalkDim },
  figure: { ...type.label, fontVariant: ['tabular-nums'] },
  unit: { fontFamily: fonts.medium, fontSize: 13, color: colors.chalkFaint },
  right: { marginLeft: 'auto', fontSize: 18, lineHeight: 24 },
  mine: { backgroundColor: colors.sunken, borderRadius: 12 },
  player: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    minHeight: 48,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.hairline,
  },
  playerRank: {
    ...type.label,
    width: 32,
    color: colors.chalkFaint,
    fontVariant: ['tabular-nums'],
  },
  you: {
    ...type.meta,
    fontFamily: fonts.semibold,
    color: colors.chalk,
    paddingHorizontal: 6,
    borderRadius: 4,
    backgroundColor: colors.edge,
  },
  team: {
    gap: 10,
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.hairline,
  },
  teamLine: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  teamRank: {
    width: 24,
    fontFamily: fonts.display,
    fontSize: 26,
    lineHeight: 28,
    color: colors.chalk,
  },
  barTrack: {
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.hairline,
    overflow: 'hidden',
  },
  bar: { height: 4, borderRadius: 2 },
  pinned: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 56,
    paddingHorizontal: 16,
    backgroundColor: colors.sunken,
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
  },
});
