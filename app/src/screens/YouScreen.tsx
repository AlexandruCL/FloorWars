import { useCallback, useEffect, useState } from 'react';
import { Alert, AppState, Platform, StyleSheet, Text } from 'react-native';
import type { CompositeScreenProps } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { revokeRefreshToken } from '../auth/logout';
import { endSession } from '../auth/session';
import { FloorSensors } from '../native/floorSensors';
import type { MainStackParamList, TabParamList } from '../navigation/types';
import { colors, Heading, Row, RowGroup, Screen, type } from '../ui/parts';

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

// Season figures and recent climbs join in the screens step.
export function YouScreen({ navigation }: Props) {
  const battery = useBatteryAllowed();
  return (
    <Screen>
      <Heading>You</Heading>
      <RowGroup>
        <Row
          title="All climbs"
          onPress={() => navigation.navigate('History')}
        />
      </RowGroup>
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
});
