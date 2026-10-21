import { useEffect, useState } from 'react';
import { Button, StyleSheet, Text, View } from 'react-native';
import { FloorSensors, requestPermissions } from './floorSensors';

// Dev-only controls for the native module until the sensor logger screen (T4).
export function FloorSensorsDebug() {
  const [status, setStatus] = useState('idle');
  const [permissions, setPermissions] = useState('');
  const [nativeStatus, setNativeStatus] = useState('');

  useEffect(() => {
    const subscription = FloorSensors.onStatusChange(event => {
      console.log('[FloorSensors] onStatusChange', event);
      setStatus(event.logging ? `logging "${event.label}"` : 'idle');
    });
    return () => subscription.remove();
  }, []);

  const onRequestPermissions = async () => {
    const results = await requestPermissions();
    console.log('[FloorSensors] permissions', results);
    setPermissions(JSON.stringify(results, null, 1));
  };

  const onGetStatus = async () => {
    const result = await FloorSensors.getStatus();
    console.log('[FloorSensors] getStatus', result);
    setNativeStatus(JSON.stringify(result));
  };

  return (
    <View style={styles.panel}>
      <Text>{`FloorSensors: ${status}`}</Text>
      <Button title="Request permissions" onPress={onRequestPermissions} />
      <Button
        title='startLogging("test")'
        onPress={() => FloorSensors.startLogging('test')}
      />
      <Button
        title="stopLogging()"
        onPress={() => FloorSensors.stopLogging()}
      />
      <Button title="getStatus()" onPress={onGetStatus} />
      <Text>{nativeStatus}</Text>
      <Text>{permissions}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    padding: 16,
    gap: 8,
  },
});
