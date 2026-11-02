import { useRef, useState } from 'react';
import { ActivityIndicator, Linking, StyleSheet, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { api, ApiError } from '../api/client';
import { DeviceError, noDeviceLibs, type CheckinDeps } from '../checkin/deps';
import { parseQrPayload } from '../checkin/qr';
import {
  errorKind,
  errorMessage,
  successText,
  type Checkin,
  type Method,
  type Phase,
} from '../checkin/state';
import type { MainStackParamList } from '../navigation/types';
import { Body, Button, colors, ErrorText, Heading, Screen } from '../ui/parts';

type Props = NativeStackScreenProps<MainStackParamList, 'Checkin'> & {
  deps?: CheckinDeps;
};

async function buildingName(id: number): Promise<string> {
  try {
    const all = await api('get', '/buildings');
    return all.find(b => b.id === id)?.name ?? `Building ${id}`;
  } catch {
    // The check-in already succeeded; a missing name must not turn it into an error.
    return `Building ${id}`;
  }
}

export function CheckinScreen({ navigation, deps = noDeviceLibs }: Props) {
  const [phase, setPhase] = useState<Phase>({ name: 'idle' });
  // The scanner fires on every frame that holds a code; only the first one counts.
  const busy = useRef(false);

  const fail = (e: unknown, method: Method) => {
    busy.current = false;
    setPhase({ name: 'error', kind: errorKind(e, method), method });
  };

  const submit = async (
    body:
      | { method: 'qr'; qr_token: string }
      | {
          method: 'geofence';
          latitude: number;
          longitude: number;
        },
  ) => {
    setPhase({ name: 'submitting' });
    try {
      const checkin: Checkin = await api('post', '/checkins', { body });
      const building = await buildingName(checkin.building_id);
      busy.current = false;
      setPhase({ name: 'success', checkin, building });
    } catch (e) {
      fail(e, body.method);
    }
  };

  const startScan = async () => {
    try {
      if (!(await deps.requestCameraPermission())) {
        return fail(new DeviceError('denied'), 'qr');
      }
    } catch (e) {
      return fail(e, 'qr');
    }
    busy.current = false;
    setPhase({ name: 'scanning' });
  };

  const onScan = (raw: string) => {
    if (busy.current) {
      return;
    }
    const parsed = parseQrPayload(raw);
    if (!parsed.ok) {
      return; // Not one of ours (a poster, a menu): keep looking.
    }
    busy.current = true;
    if (parsed.expired) {
      return fail(
        new ApiError(403, { type: 'urn:floorwars:problem:qr-expired' }),
        'qr',
      );
    }
    submit({ method: 'qr', qr_token: parsed.token });
  };

  const useLocation = async () => {
    setPhase({ name: 'locating' });
    try {
      const { latitude, longitude } = await deps.getPosition();
      await submit({ method: 'geofence', latitude, longitude });
    } catch (e) {
      fail(e, 'geofence');
    }
  };

  const { ScannerView } = deps;
  return (
    <Screen>
      {phase.name === 'idle' && (
        <>
          <Heading>Check in</Heading>
          <Body>
            Scan the code at the building entrance. No code in sight? Use your
            location instead.
          </Body>
          <Button title="Scan entrance code" onPress={startScan} />
          <Button title="Use my location" secondary onPress={useLocation} />
        </>
      )}
      {phase.name === 'scanning' && (
        <>
          <Heading>Scan the code</Heading>
          <View style={styles.camera}>
            <ScannerView onScan={onScan} />
          </View>
          <Body>Hold the phone so the whole code is in the frame.</Body>
          <Button
            title="Cancel"
            secondary
            onPress={() => setPhase({ name: 'idle' })}
          />
        </>
      )}
      {(phase.name === 'locating' || phase.name === 'submitting') && (
        <>
          <ActivityIndicator
            accessibilityLabel="Checking in"
            color={colors.accent}
            size="large"
          />
          <Body>
            {phase.name === 'locating'
              ? 'Finding your position...'
              : 'Checking in...'}
          </Body>
        </>
      )}
      {phase.name === 'success' && (
        <>
          <Heading>{successText(phase.building, phase.checkin)}</Heading>
          <Button title="Done" onPress={() => navigation.goBack()} />
        </>
      )}
      {phase.name === 'error' && (
        <>
          <Heading>Not checked in</Heading>
          <ErrorText message={errorMessage(phase.kind, phase.method)} />
          {phase.kind === 'denied' && (
            <Button
              title="Open Settings"
              onPress={() => Linking.openSettings()}
            />
          )}
          <Button
            title={
              phase.method === 'qr' ? 'Scan again' : 'Try my location again'
            }
            secondary={phase.kind === 'denied'}
            onPress={phase.method === 'qr' ? startScan : useLocation}
          />
          <Button
            title={
              phase.method === 'qr' ? 'Use my location' : 'Scan entrance code'
            }
            secondary
            onPress={phase.method === 'qr' ? useLocation : startScan}
          />
        </>
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
