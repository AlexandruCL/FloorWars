import Geolocation from '@react-native-community/geolocation';
import { PermissionsAndroid, StyleSheet } from 'react-native';
import { VisionCamera } from 'react-native-vision-camera';
import { CodeScanner } from 'react-native-vision-camera-barcode-scanner';
import { DeviceError, type CheckinDeps, type Position } from './deps';

function ScannerView({ onScan }: { onScan: (raw: string) => void }) {
  return (
    <CodeScanner
      style={StyleSheet.absoluteFill}
      isActive
      barcodeFormats={['qr-code']}
      onBarcodeScanned={codes => {
        for (const c of codes) {
          if (c.rawValue) {
            onScan(c.rawValue);
          }
        }
      }}
      onError={() => {}}
    />
  );
}

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
