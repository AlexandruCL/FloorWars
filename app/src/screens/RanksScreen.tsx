import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { api } from '../api/client';
import { pullToRefresh, ReadState, useRead } from '../data/useRead';
import { FloorSensors } from '../native/floorSensors';
import { Body, colors, Heading, Screen, type } from '../ui/parts';

type Scope = 'individual' | 'team' | 'building';
const TABS: { scope: Scope; label: string }[] = [
  { scope: 'individual', label: 'Individual' },
  { scope: 'team', label: 'Team' },
  { scope: 'building', label: 'Building' },
];
const LIMIT = 50;

// GET /seasons may not be deployed yet (contract 0.8.0): then only the active season is offered.
async function loadSeasons() {
  const active = await api('get', '/seasons/active');
  const all = await api('get', '/seasons').catch(() => []);
  return {
    activeId: active.id,
    ids: all.some(s => s.id === active.id)
      ? all.map(s => s.id)
      : [active.id, ...all.map(s => s.id)],
  };
}

function Chips<T extends string | number>({
  items,
  selected,
  onSelect,
  role,
}: {
  items: { value: T; label: string }[];
  selected: T | null;
  onSelect: (v: T) => void;
  role: 'tab' | 'radio';
}) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false}>
      <View style={styles.chips}>
        {items.map(i => (
          <Pressable
            key={String(i.value)}
            accessibilityRole={role}
            accessibilityState={{ selected: i.value === selected }}
            onPress={() => onSelect(i.value)}
            style={[styles.chip, i.value === selected && styles.chipOn]}
          >
            <Text
              style={i.value === selected ? styles.chipTextOn : styles.chipText}
            >
              {i.label}
            </Text>
          </Pressable>
        ))}
      </View>
    </ScrollView>
  );
}

export function RanksScreen() {
  const [scope, setScope] = useState<Scope>('individual');
  const [season, setSeason] = useState<number | null>(null);
  const [building, setBuilding] = useState<number | null>(null);

  const seasons = useRead('seasons', loadSeasons);
  const buildings = useRead('buildings', () => api('get', '/buildings'));

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

  return (
    <Screen refreshControl={pullToRefresh(board)}>
      <Heading>Ranks</Heading>
      <Chips
        role="tab"
        items={TABS.map(t => ({ value: t.scope, label: t.label }))}
        selected={scope}
        onSelect={setScope}
      />
      {seasons.data && (
        <Chips
          role="radio"
          items={seasons.data.ids.map(id => ({
            value: id,
            label: `Season ${id}`,
          }))}
          selected={season}
          onSelect={setSeason}
        />
      )}
      {needsBuilding && buildings.data && (
        <Chips
          role="radio"
          items={buildings.data.map(b => ({ value: b.id, label: b.name }))}
          selected={building}
          onSelect={setBuilding}
        />
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
          {board.data &&
            (board.data.entries.length === 0 ? (
              <Body>No points on this board yet this season.</Body>
            ) : (
              board.data.entries.map(e => (
                <View
                  key={`${e.rank}:${e.id}`}
                  style={styles.row}
                  accessible
                  accessibilityLabel={`${e.rank}. ${e.name}, ${e.points} points`}
                >
                  <Text style={styles.rank}>{e.rank}</Text>
                  <Text style={styles.name}>{e.name}</Text>
                  <Text style={styles.points}>{`${e.points} points`}</Text>
                </View>
              ))
            ))}
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  chips: { flexDirection: 'row', gap: 8 },
  chip: {
    minHeight: 44,
    paddingHorizontal: 16,
    justifyContent: 'center',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.edge,
  },
  chipOn: { backgroundColor: colors.chalk, borderColor: colors.chalk },
  chipText: { ...type.body, color: colors.chalk },
  chipTextOn: { ...type.label, color: colors.night },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.hairline,
  },
  rank: {
    ...type.label,
    width: 32,
    color: colors.chalkFaint,
    fontVariant: ['tabular-nums'],
  },
  name: { ...type.label, flex: 1 },
  points: { ...type.label, fontVariant: ['tabular-nums'] },
});
