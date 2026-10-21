import { Button, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { DEV_SKIP_SIGN_IN } from '../config/devFlags';
import { FloorSensorsDebug } from '../native/FloorSensorsDebug';
import type { MainStackParamList } from '../navigation/types';

function Placeholder({ title }: { title: string }) {
  return (
    <View style={styles.container}>
      <Text>{title}</Text>
    </View>
  );
}

// onStubSignIn is the auth stub (T7). onDevSkipSignIn opens Main without a token while DEV_SKIP_SIGN_IN is on.
export function SignInScreen({
  onStubSignIn,
  onDevSkipSignIn,
}: {
  onStubSignIn?: () => Promise<void>;
  onDevSkipSignIn?: () => void;
}) {
  return (
    <>
      <Placeholder title="Sign in" />
      {onStubSignIn && (
        <Button
          title="Sign in (stub)"
          onPress={() =>
            onStubSignIn().catch(e =>
              console.warn('[auth] stub sign-in failed', e),
            )
          }
        />
      )}
      {DEV_SKIP_SIGN_IN && onDevSkipSignIn && (
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
