import { StyleSheet, Text, View } from 'react-native';
import { FloorSensorsDebug } from '../native/FloorSensorsDebug';

function Placeholder({ title }: { title: string }) {
  return (
    <View style={styles.container}>
      <Text>{title}</Text>
    </View>
  );
}

export function SignInScreen() {
  return (
    <>
      <Placeholder title="Sign in" />
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
