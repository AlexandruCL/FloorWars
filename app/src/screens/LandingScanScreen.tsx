import { useEffect, useRef, useState } from 'react';
import { Linking, StyleSheet, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { CheckinDeps } from '../checkin/deps';
import { deviceLibs } from '../checkin/deviceLibs';
import { errorMessage } from '../checkin/state';
import {
  cooldownMsLeft,
  submitLandingScan,
  type ScanResult,
} from '../landing/landingScan';
import { FloorSensors } from '../native/floorSensors';
import type { ActiveCheckin } from '../native/NativeFloorSensors';
import type { MainStackParamList } from '../navigation/types';
import { Body, Button, colors, ErrorText, Heading, Screen } from '../ui/parts';

type Props = NativeStackScreenProps<MainStackParamList, 'LandingScan'> & {
  deps?: CheckinDeps;
};

export function LandingScanScreen({ navigation, deps = deviceLibs }: Props) {
  // undefined: still reading; null: no usable check-in.
  const [checkin, setCheckin] = useState<ActiveCheckin | null | undefined>();
  const [scanning, setScanning] = useState(false);
  const [denied, setDenied] = useState(false);
  const [result, setResult] = useState<ScanResult | null>(null);
  // The scanner fires on every frame that holds a code; only the first one counts.
  const busy = useRef(false);

  useEffect(() => {
    FloorSensors.getActiveCheckin()
      .then(c => setCheckin(c && c.valid_until_ms > Date.now() ? c : null))
      .catch(() => setCheckin(null));
  }, []);

  if (checkin === undefined) {
    return (
      <Screen>
        <Body>Loading...</Body>
      </Screen>
    );
  }
  if (checkin === null) {
    return (
      <Screen>
        <Body>
          Check in at the building first, then scan the sticker on a stair
          landing.
        </Body>
        <Button
          title="Check in"
          onPress={() => navigation.replace('Checkin')}
        />
      </Screen>
    );
  }

  const name = checkin.building_name ?? `Building ${checkin.building_id}`;
  const left = cooldownMsLeft(checkin.building_id);

  const start = async () => {
    setResult(null);
    setDenied(false);
    try {
      if (!(await deps.requestCameraPermission())) {
        return setDenied(true);
      }
    } catch {
      return setDenied(true);
    }
    busy.current = false;
    setScanning(true);
  };

  const onScan = async (raw: string) => {
    if (busy.current) {
      return;
    }
    busy.current = true;
    setScanning(false);
    setResult(await submitLandingScan(checkin.building_id, raw));
  };

  return (
    <Screen>
      <Heading>{`Scan at the stairs of ${name}`}</Heading>
      <Body>
        Your phone has no barometer, so it can't measure climbs. Scan the
        sticker on a stair landing instead.
      </Body>
      {scanning && (
        <>
          <View style={styles.camera}>
            <deps.ScannerView onScan={onScan} />
          </View>
          <Button title="Cancel" secondary onPress={() => setScanning(false)} />
        </>
      )}
      {result &&
        (result.kind === 'ok' ? (
          <Body>{result.text}</Body>
        ) : (
          <ErrorText message={result.text} />
        ))}
      {denied && (
        <>
          <ErrorText message={errorMessage('denied', 'qr')} />
          <Button
            title="Open Settings"
            onPress={() => Linking.openSettings()}
          />
        </>
      )}
      {!scanning && left > 0 && result === null && (
        <Body>{`You can scan again in this building in ${Math.ceil(
          left / 60000,
        )} min.`}</Body>
      )}
      {!scanning && left === 0 && (
        <Button title="Scan sticker" onPress={start} />
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  camera: {
    height: 320,
    borderRadius: 8,
    overflow: 'hidden',
    backgroundColor: colors.ink,
  },
});
