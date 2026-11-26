import { useRef, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { api, ApiError } from '../api/client';
import { setActiveCheckin } from '../checkin/active';
import { DeviceError, type CheckinDeps } from '../checkin/deps';
import { deviceLibs } from '../checkin/deviceLibs';
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
import {
  Body,
  Button,
  colors,
  ErrorText,
  Heading,
  Screen,
  type,
} from '../ui/parts';

type Props = NativeStackScreenProps<MainStackParamList, 'Checkin'> & {
  deps?: CheckinDeps;
};

// Null when unknown: GET /buildings may not exist on the server yet.
async function buildingName(id: number): Promise<string | null> {
  try {
    const all = await api('get', '/buildings');
    return all.find(b => b.id === id)?.name ?? null;
  } catch {
    // The check-in already succeeded; a missing name must not turn it into an error.
    return null;
  }
}

export function CheckinScreen({ navigation, deps = deviceLibs }: Props) {
  const [phase, setPhase] = useState<Phase>({ name: 'idle' });
  const { bottom } = useSafeAreaInsets();
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
      const name = await buildingName(checkin.building_id);
      await setActiveCheckin(checkin, name);
      busy.current = false;
      setPhase({
        name: 'success',
        checkin,
        building: name ?? `Building ${checkin.building_id}`,
      });
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
  // Full-screen dark camera with one line (DESIGN.md section 10).
  if (phase.name === 'scanning') {
    return (
      <View style={styles.cameraScreen}>
        <ScannerView onScan={onScan} />
        <View style={[styles.cameraBar, { paddingBottom: 16 + bottom }]}>
          <Text style={styles.cameraLine}>
            Point the camera at the code by the entrance.
          </Text>
          <Button
            title="Cancel"
            variant="text"
            onPress={() => setPhase({ name: 'idle' })}
          />
        </View>
      </View>
    );
  }
  return (
    <Screen>
      {phase.name === 'idle' && (
        <>
          <Body>
            Scan the code at the building entrance. No code in sight? Use your
            location instead.
          </Body>
          <Button title="Scan entrance code" onPress={startScan} />
          <Button
            title="Use my location"
            variant="text"
            onPress={useLocation}
          />
        </>
      )}
      {(phase.name === 'locating' || phase.name === 'submitting') && (
        <>
          <ActivityIndicator
            accessibilityLabel="Checking in"
            color={colors.chalk}
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
            variant={phase.kind === 'denied' ? 'text' : 'primary'}
            onPress={phase.method === 'qr' ? startScan : useLocation}
          />
          <Button
            title={
              phase.method === 'qr' ? 'Use my location' : 'Scan entrance code'
            }
            variant="text"
            onPress={phase.method === 'qr' ? useLocation : startScan}
          />
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  cameraScreen: { flex: 1, backgroundColor: colors.night },
  cameraBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: 'center',
    gap: 4,
    paddingTop: 16,
    paddingHorizontal: 16,
    backgroundColor: colors.night,
  },
  cameraLine: { ...type.body, color: colors.chalk, textAlign: 'center' },
});
