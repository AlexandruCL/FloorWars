import { Alert, Button, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { revokeRefreshToken } from '../auth/logout';
import { endSession } from '../auth/session';
import { FloorSensors } from '../native/floorSensors';
import type { MainStackParamList } from '../navigation/types';

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

function Placeholder({ title }: { title: string }) {
  return (
    <View style={styles.container}>
      <Text>{title}</Text>
    </View>
  );
}

export function HomeScreen({
  navigation,
}: NativeStackScreenProps<MainStackParamList, 'Home'>) {
  return (
    <>
      <Placeholder title="Home" />
      <Button title="Check in" onPress={() => navigation.navigate('Checkin')} />
      <Button
        title="Sensor logger"
        onPress={() => navigation.navigate('SensorLogger')}
      />
      <Button title="Sign out" onPress={confirmSignOut} />
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
