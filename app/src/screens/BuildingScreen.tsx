import { useEffect, useRef } from 'react';
import { StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { api } from '../api/client';
import { pullToRefresh, ReadState, useRead } from '../data/useRead';
import type { MainStackParamList } from '../navigation/types';
import { useGameEvents } from '../realtime/useGameEvents';
import { BuildingDrawing } from '../standings/BuildingDrawing';
import { Body, colors, Heading, Screen, type } from '../ui/parts';

export const FLIP_ANIMATION_MS = 600;

export function BuildingScreen({
  route,
}: NativeStackScreenProps<MainStackParamList, 'Building'>) {
  // A deep link delivers the param as a string.
  const id = Number(route.params.buildingId);
  const standings = useRead(`standings:${id}`, () =>
    api('get', '/buildings/{id}/standings', { path: { id } }),
  );
  const buildings = useRead('buildings', () => api('get', '/buildings'));
  const name = buildings.data?.find(b => b.id === id)?.name ?? `Building ${id}`;

  const data = standings.data;
  const ownerColor = useSharedValue<string>(colors.hairline);
  useEffect(() => {
    ownerColor.value = data?.owner?.color_hex ?? colors.hairline;
  }, [data, ownerColor]);
  const swatch = useAnimatedStyle(() => ({
    backgroundColor: ownerColor.value,
  }));

  const teamsRef = useRef(data?.teams ?? []);
  teamsRef.current = data?.teams ?? [];
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const refetch = standings.refresh;
  useEffect(() => () => clearTimeout(timer.current), []);
  useGameEvents(e => {
    if (e.type !== 'building_flipped' || e.building_id !== id) {
      return;
    }
    const colorOf = (code: string | null) =>
      teamsRef.current.find(t => t.code === code)?.color_hex ?? colors.hairline;
    ownerColor.value = colorOf(e.from_team);
    ownerColor.value = withTiming(colorOf(e.to_team), {
      duration: FLIP_ANIMATION_MS,
    });
    clearTimeout(timer.current);
    timer.current = setTimeout(refetch, FLIP_ANIMATION_MS);
  });

  const teams = data ? [...data.teams].sort((a, b) => b.points - a.points) : [];
  const { width } = useWindowDimensions();

  return (
    <Screen refreshControl={pullToRefresh(standings)}>
      <BuildingDrawing
        buildingId={id}
        teams={teams}
        owner={data?.owner?.code ?? null}
        name={name}
        width={width - 32}
        height={240}
      />
      <Heading>{name}</Heading>
      <ReadState
        read={standings}
        notFoundText="This building doesn't exist anymore."
      />
      {data && (
        <>
          <View style={styles.owner}>
            <Animated.View style={[styles.swatch, swatch]} />
            <Text style={styles.ownerText}>
              {data.owner
                ? `Owned by ${data.owner.code}`
                : 'Nobody owns this building yet'}
            </Text>
          </View>
          {teams.length === 0 ? (
            <Body>
              No team has points here in the last 7 days. Climb the stairs to
              claim it.
            </Body>
          ) : (
            <>
              {teams.map(t => (
                <View
                  key={t.team_id}
                  style={styles.team}
                  accessible
                  accessibilityLabel={`${t.code}: ${t.points} points`}
                >
                  <View
                    style={[styles.dot, { backgroundColor: t.color_hex }]}
                  />
                  <Text style={styles.code}>{t.code}</Text>
                  <Text style={styles.points}>{`${t.points} points`}</Text>
                </View>
              ))}
            </>
          )}
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  owner: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  swatch: { width: 24, height: 24, borderRadius: 12 },
  ownerText: type.heading,
  team: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.hairline,
  },
  dot: { width: 14, height: 14, borderRadius: 7 },
  code: { ...type.label, flex: 1 },
  points: { ...type.label, fontVariant: ['tabular-nums'] },
});
