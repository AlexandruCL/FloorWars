import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { CompositeScreenProps } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { api } from '../api/client';
import type { components } from '../api/schema';
import { useActiveCheckin } from '../checkin/active';
import { useMe } from '../data/myTeam';
import { pullToRefresh, ReadState, useRead } from '../data/useRead';
import type { MainStackParamList, TabParamList } from '../navigation/types';
import { BuildingDrawing } from '../standings/BuildingDrawing';
import { standingsOrder } from '../standings/facade';
import { ownerLine } from '../standings/fight';
import { Pictogram } from '../ui/Pictogram';
import {
  Body,
  colors,
  fonts,
  Heading,
  Screen,
  TeamTag,
  type,
} from '../ui/parts';

type Props = CompositeScreenProps<
  BottomTabScreenProps<TabParamList, 'Buildings'>,
  NativeStackScreenProps<MainStackParamList>
>;
type Standings = components['schemas']['BuildingStandings'];

// shortcut: one standings call per building, fine for the pilot's few buildings; past about 20 it
// needs a list endpoint with owners (DESIGN.md section 15).
async function allStandings(ids: number[]) {
  const results = await Promise.allSettled(
    ids.map(id => api('get', '/buildings/{id}/standings', { path: { id } })),
  );
  const byId = new Map<number, Standings>();
  results.forEach(
    (r, i) => r.status === 'fulfilled' && byId.set(ids[i], r.value),
  );
  return byId;
}

// Every building and who holds it, with the score of buildings held per team (DESIGN.md section 10).
export function BuildingsScreen({ navigation }: Props) {
  const buildings = useRead('buildings', () => api('get', '/buildings'));
  const ids = (buildings.data ?? []).map(b => b.id);
  const standings = useRead(
    ids.length ? `standings:all:${ids.join(',')}` : null,
    () => allStandings(ids),
  );
  const here = useActiveCheckin(navigation);
  const season = useMe().data?.season;

  // Your building first, then by name.
  const list = [...(buildings.data ?? [])].sort(
    (a, b) =>
      Number(b.id === here?.building_id) - Number(a.id === here?.building_id) ||
      a.name.localeCompare(b.name),
  );

  // Buildings held per team, most first, then how many are open.
  const held = new Map<string, { color: string; count: number }>();
  let open = 0;
  for (const s of standings.data?.values() ?? []) {
    if (s.owner) {
      const h = held.get(s.owner.code) ?? {
        color: s.owner.color_hex,
        count: 0,
      };
      held.set(s.owner.code, { ...h, count: h.count + 1 });
    } else {
      open += 1;
    }
  }
  const tally = [...held.entries()].sort((a, b) => b[1].count - a[1].count);

  return (
    <Screen
      refreshControl={pullToRefresh({
        refreshing: buildings.refreshing || standings.refreshing,
        refresh: () => {
          buildings.refresh();
          standings.refresh();
        },
      })}
    >
      <View style={styles.titleRow}>
        <Heading>Buildings</Heading>
        {season && <Text style={styles.sub}>{`Season ${season.id}`}</Text>}
      </View>
      {buildings.failure && !buildings.data ? (
        <Text style={styles.error}>
          {"Couldn't load the buildings. Pull down to try again."}
        </Text>
      ) : (
        <ReadState read={buildings} />
      )}
      {buildings.data && list.length === 0 && (
        <Body>No buildings are set up for this season yet.</Body>
      )}
      {standings.data && list.length > 0 && (
        <View style={styles.tallyBlock}>
          <Text style={type.meta}>Held now</Text>
          <View style={styles.tally}>
            {tally.map(([code, h]) => (
              <View
                key={code}
                style={styles.tallyItem}
                accessible
                accessibilityLabel={`${code} holds ${h.count}`}
              >
                <TeamTag code={code} color={h.color} size="medium" />
                <Text style={styles.count}>{h.count}</Text>
              </View>
            ))}
            {open > 0 && <Text style={styles.open}>{`${open} open`}</Text>}
          </View>
        </View>
      )}
      <View>
        {list.map(b => {
          const s = standings.data?.get(b.id);
          const owner = s?.owner?.code ?? null;
          const teams = s ? standingsOrder(s.teams, owner) : [];
          const line = s ? ownerLine(teams, owner) : null;
          const tag = line?.code
            ? teams.find(t => t.code === line.code)
            : undefined;
          const isHere = b.id === here?.building_id;
          return (
            <Pressable
              key={b.id}
              accessibilityRole="button"
              accessibilityLabel={[
                b.name,
                line ? `${line.code ? `${line.code} ` : ''}${line.text}` : null,
                isHere ? "You're here" : null,
              ]
                .filter(Boolean)
                .join(', ')}
              onPress={() =>
                navigation.navigate('Building', { buildingId: b.id })
              }
              style={({ pressed }) => [styles.row, pressed && styles.pressed]}
            >
              <BuildingDrawing
                buildingId={b.id}
                teams={teams}
                owner={owner}
                width={48}
                height={64}
              />
              <View style={styles.rowText}>
                <Text style={type.label} numberOfLines={2}>
                  {b.name}
                </Text>
                {line ? (
                  <View style={styles.ownerLine}>
                    {tag && <TeamTag code={tag.code} color={tag.color_hex} />}
                    <Text style={styles.sub}>{line.text}</Text>
                  </View>
                ) : standings.data ? (
                  <Text style={styles.sub}>Standings unavailable</Text>
                ) : null}
              </View>
              {isHere ? (
                <Text style={styles.here}>You're here</Text>
              ) : (
                <Pictogram name="chevron" size={20} color={colors.chalkFaint} />
              )}
            </Pressable>
          );
        })}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  titleRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
  },
  sub: { ...type.meta, color: colors.chalkDim, flexShrink: 1 },
  error: { ...type.body, color: colors.bad },
  tallyBlock: { gap: 6 },
  tally: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    columnGap: 18,
    rowGap: 8,
  },
  tallyItem: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  count: {
    fontFamily: fonts.display,
    fontSize: 28,
    lineHeight: 32,
    color: colors.chalk,
  },
  open: { ...type.label, color: colors.chalkDim },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    minHeight: 80,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: colors.hairline,
  },
  pressed: { backgroundColor: colors.sunken },
  rowText: { flex: 1, gap: 4 },
  ownerLine: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  here: {
    ...type.meta,
    fontFamily: fonts.semibold,
    color: colors.chalk,
    paddingVertical: 2,
    paddingHorizontal: 8,
    borderRadius: 4,
    backgroundColor: colors.sunken,
  },
});
