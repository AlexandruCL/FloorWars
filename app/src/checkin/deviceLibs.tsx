import Geolocation from '@react-native-community/geolocation';
import { PermissionsAndroid, StyleSheet, View } from 'react-native';
import {
  Camera,
  useCameraDevice,
  VisionCamera,
} from 'react-native-vision-camera';
import { useBarcodeScannerOutput } from 'react-native-vision-camera-barcode-scanner';
import { Body } from '../ui/parts';
import { DeviceError, type CheckinDeps, type Position } from './deps';

// Not CodeScanner: it throws while Vision Camera is still loading its device list.
export function ScannerView({ onScan }: { onScan: (raw: string) => void }) {
  const device = useCameraDevice('back');
  const output = useBarcodeScannerOutput({
    barcodeFormats: ['qr-code'],
    onBarcodeScanned: codes => {
      for (const c of codes) {
        if (c.rawValue) {
          onScan(c.rawValue);
        }
      }
    },
    onError: () => {},
  });
  if (device == null) {
    return (
      <View style={styles.starting}>
        <Body>Starting camera...</Body>
      </View>
    );
  }
  return (
    <Camera
      style={StyleSheet.absoluteFill}
      isActive
      device={device}
      outputs={[output]}
    />
  );
}

const styles = StyleSheet.create({
  starting: { flex: 1, alignItems: 'center', justifyContent: 'center' },
});

async function getPosition(): Promise<Position> {
  const granted = await PermissionsAndroid.request(
    PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
  );
  if (granted !== PermissionsAndroid.RESULTS.GRANTED) {
    throw new DeviceError('denied');
  }
  return new Promise((resolve, reject) =>
    Geolocation.getCurrentPosition(
      ({ coords }) =>
        resolve({ latitude: coords.latitude, longitude: coords.longitude }),
      err => reject(new DeviceError(err.code === 1 ? 'denied' : 'unavailable')),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 10000 },
    ),
  );
}

export const deviceLibs: CheckinDeps = {
  ScannerView,
  requestCameraPermission: () => VisionCamera.requestCameraPermission(),
  getPosition,
};
