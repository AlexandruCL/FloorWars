import { Button, StyleSheet, Text, View } from 'react-native';
import { FloorSensorsDebug } from '../native/FloorSensorsDebug';

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

export function HomeScreen() {
  return <Placeholder title="Home" />;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
