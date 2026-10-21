import { Button, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { FloorSensorsDebug } from '../native/FloorSensorsDebug';
import type { MainStackParamList } from '../navigation/types';

function Placeholder({ title }: { title: string }) {
  return (
    <View style={styles.container}>
      <Text>{title}</Text>
    </View>
  );
}

// onDevSkipSignIn opens the Main stack in dev builds until the auth stub (T7) exists.
export function SignInScreen({
  onDevSkipSignIn,
}: {
  onDevSkipSignIn?: () => void;
}) {
  return (
    <>
      <Placeholder title="Sign in" />
      {__DEV__ && onDevSkipSignIn && (
        <Button title="Skip sign-in (dev)" onPress={onDevSkipSignIn} />
      )}
      {__DEV__ && <FloorSensorsDebug />}
    </>
  );
}

export function HomeScreen({
  navigation,
}: NativeStackScreenProps<MainStackParamList, 'Home'>) {
  return (
    <>
      <Placeholder title="Home" />
      <Button
        title="Sensor logger"
        onPress={() => navigation.navigate('SensorLogger')}
      />
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
