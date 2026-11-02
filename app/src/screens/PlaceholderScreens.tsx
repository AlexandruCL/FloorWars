import { Button, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { MainStackParamList } from '../navigation/types';

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
