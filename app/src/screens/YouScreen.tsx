import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  AppState,
  Platform,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import type { CompositeScreenProps } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { revokeRefreshToken } from '../auth/logout';
import { endSession } from '../auth/session';
import { seasonText, useMe } from '../data/myTeam';
import { clock, ReadState, useRead } from '../data/useRead';
import { ClimbStatus, climbDetail, statusWord } from '../history/ClimbStatus';
import { fetchSegmentPage } from '../history/today';
import { FloorSensors } from '../native/floorSensors';
import type { MainStackParamList, TabParamList } from '../navigation/types';
import {
  FLOOR_EQUIVALENT_LABEL,
  floorEquivalent,
} from '../scoring/floorEquivalent';
import {
  Body,
  colors,
  fonts,
  Heading,
  Row,
  RowGroup,
  Screen,
  TeamTag,
  type,
} from '../ui/parts';
import { ordinal } from './RanksScreen';

type Props = CompositeScreenProps<
  BottomTabScreenProps<TabParamList, 'You'>,
  NativeStackScreenProps<MainStackParamList>
>;

export async function confirmSignOut() {
  const n = await FloorSensors.getPendingCount().catch(() => 0);
  Alert.alert(
    'Sign out?',
    n > 0
      ? `${n} ${
          n === 1 ? 'climb is' : 'climbs are'
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

// null: unknown (the read failed or not Android).
function useBatteryAllowed(): boolean | null {
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const read = useCallback(() => {
    FloorSensors.isIgnoringBatteryOptimizations().then(setAllowed, () =>
      setAllowed(null),
    );
  }, []);
  useEffect(() => {
    if (Platform.OS !== 'android') {
      return undefined;
    }
    read();
    // Back from the battery settings: read again.
    const sub = AppState.addEventListener('change', s => {
      if (s === 'active') {
        read();
      }
    });
    return () => sub.remove();
  }, [read]);
  return allowed;
}

// Your season and settings (DESIGN.md section 10).
export function YouScreen({ navigation }: Props) {
  const battery = useBatteryAllowed();
  const me = useMe();
  const recent = useRead('history:first', () => fetchSegmentPage());
  const team = me.data?.team;
  const stats = me.data?.stats;
  return (
    <Screen>
      {team && me.data ? (
        <View style={styles.header}>
          <TeamTag code={team.code} color={team.color_hex} size="jersey" />
          <View style={styles.headerText}>
            <Text style={styles.title} accessibilityRole="header">
              {`You climb for ${team.code}`}
            </Text>
            <Text style={styles.sub}>{seasonText(me.data.season)}</Text>
          </View>
        </View>
      ) : (
        <Heading>You</Heading>
      )}
      <ReadState read={me} />
      {stats && (
        <View style={styles.figures}>
          <View style={styles.figureWide}>
            <Text style={type.display}>
              {floorEquivalent(stats.steps_verified)}
            </Text>
            <Text style={styles.sub}>{FLOOR_EQUIVALENT_LABEL}</Text>
          </View>
          <View style={styles.figure}>
            <Text style={styles.number}>
              {stats.points.toLocaleString('en-US')}
            </Text>
            <Text style={styles.sub}>
              {stats.points === 1 ? 'point' : 'points'}
            </Text>
          </View>
          <View style={styles.figure}>
            <Text style={styles.number}>
              {stats.rank ? ordinal(stats.rank) : '-'}
            </Text>
            <Text style={styles.sub}>in Players</Text>
          </View>
        </View>
      )}
      <View>
        <Text style={[type.heading, styles.recentTitle]}>Recent climbs</Text>
        {recent.data?.items.length === 0 && (
          <Body>
            No climbs yet. Check in at a building and take the stairs.
          </Body>
        )}
        {recent.data?.items.slice(0, 3).map(c => (
          <View
            key={c.id}
            style={styles.climb}
            accessible
            accessibilityLabel={`${clock(
              Date.parse(c.started_at),
            )}, ${climbDetail(c)}, ${statusWord(c)}`}
          >
            <Text style={styles.time}>{clock(Date.parse(c.started_at))}</Text>
            <Text style={[styles.sub, styles.grow]}>{climbDetail(c)}</Text>
            <ClimbStatus item={c} />
          </View>
        ))}
        <Row
          title="All climbs"
          onPress={() => navigation.navigate('History')}
        />
      </View>
      <RowGroup>
        {Platform.OS === 'android' && (
          <Row
            title="Keep detection running"
            value={
              battery === null ? undefined : battery ? 'Allowed' : 'Restricted'
            }
            onPress={() => FloorSensors.openBatteryOptimizationSettings()}
          />
        )}
        <Row
          title="How FloorWars works"
          onPress={() => navigation.navigate('Onboarding')}
        />
      </RowGroup>
      <Text style={styles.section}>For testers</Text>
      <RowGroup>
        <Row
          title="Sensor logger"
          onPress={() => navigation.navigate('SensorLogger')}
        />
      </RowGroup>
      <RowGroup>
        <Row title="Sign out" danger onPress={confirmSignOut} />
      </RowGroup>
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { ...type.meta, color: colors.chalkDim, marginBottom: -8 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  headerText: { flex: 1, gap: 2 },
  title: { ...type.title, fontSize: 28, lineHeight: 30 },
  sub: { ...type.meta, color: colors.chalkDim },
  figures: { flexDirection: 'row', alignItems: 'flex-end', gap: 12 },
  figureWide: { flex: 1.3, gap: 6 },
  figure: { flex: 1, gap: 6 },
  number: {
    fontFamily: fonts.display,
    fontSize: 32,
    lineHeight: 34,
    color: colors.chalk,
  },
  recentTitle: { marginBottom: 4 },
  climb: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    minHeight: 48,
    borderBottomWidth: 1,
    borderBottomColor: colors.hairline,
  },
  time: { ...type.label, width: 56, fontVariant: ['tabular-nums'] },
  grow: { flex: 1 },
});
