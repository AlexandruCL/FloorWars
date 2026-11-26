import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  Button as NativeButton,
  Pressable,
  Text,
  TextInput,
  View,
} from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { api, ApiError } from '../api/client';
import type { components } from '../api/schema';
import { getDeviceInfo } from '../auth/device';
import { describeError, EMAIL_RE, OTP_RE } from '../auth/errors';
import { markTeamChosen, saveTokens } from '../auth/session';
import { DEV_SKIP_SIGN_IN } from '../config/devFlags';
import { FloorSensorsDebug } from '../native/FloorSensorsDebug';
import type { AuthStackParamList } from '../navigation/types';
import { BuildingDrawing } from '../standings/BuildingDrawing';
import { Pictogram } from '../ui/Pictogram';
import { teamTone } from '../ui/tone';
import {
  Body,
  Button,
  colors,
  ErrorText,
  fonts,
  Heading,
  inputStyle,
  Screen,
  type,
} from '../ui/parts';

type Team = components['schemas']['Team'];

// Neutral lit windows for the sign-in skyline: [id, width, height].
const SKYLINE: [number, number, number][] = [
  [14, 76, 96],
  [12, 60, 150],
  [8, 104, 120],
  [5, 76, 100],
];
const LIT = [{ code: '', color_hex: '#B4BBC6', points: 1 }];
type Nav<K extends keyof AuthStackParamList> = NativeStackScreenProps<
  AuthStackParamList,
  K
>;

async function requestCode(email: string) {
  await api('post', '/auth/otp', { body: { email } });
}

function Check({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityLabel={label}
      accessibilityState={{ checked: value }}
      onPress={() => onChange(!value)}
      style={styles.check}
    >
      <View style={[styles.box, value && styles.boxOn]}>
        {value && <Pictogram name="check" size={18} color={colors.night} />}
      </View>
      <Text style={styles.checkLabel}>{label}</Text>
    </Pressable>
  );
}

export function EmailScreen({
  navigation,
  onDevSkipSignIn,
}: Nav<'Email'> & { onDevSkipSignIn?: () => void }) {
  const [email, setEmail] = useState('');
  const [adult, setAdult] = useState(false);
  const [terms, setTerms] = useState(false);
  // Validation errors clear when their input changes; server errors only on an e-mail edit.
  const [invalid, setInvalid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const value = email.trim().toLowerCase();
    if (!EMAIL_RE.test(value) || value.length > 254) {
      setInvalid('Enter a valid e-mail address, like name@university.ro.');
      return;
    }
    if (!adult || !terms) {
      setInvalid(
        'Confirm you are 18 or older and accept the terms to continue.',
      );
      return;
    }
    setError(null);
    setInvalid(null);
    setBusy(true);
    try {
      await requestCode(value);
      navigation.navigate('Otp', { email: value });
    } catch (e) {
      setError(describeError(e, 'otp'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      {/* A strip of neutral lit buildings; the wordmark is type only until a real logo exists. */}
      <View style={styles.skyline} accessibilityElementsHidden>
        {SKYLINE.map(([id, w, h]) => (
          <BuildingDrawing
            key={id}
            buildingId={id}
            teams={LIT}
            owner={null}
            width={w}
            height={h}
          />
        ))}
      </View>
      <Text style={styles.wordmark}>FloorWars</Text>
      <Text style={styles.signTitle} accessibilityRole="header">
        Climb for your faculty
      </Text>
      <Body>Enter your university e-mail. We send you a 6-digit code.</Body>
      <Text style={styles.fieldLabel}>University e-mail</Text>
      <TextInput
        accessibilityLabel="University e-mail"
        autoCapitalize="none"
        autoComplete="email"
        autoCorrect={false}
        keyboardType="email-address"
        maxLength={254}
        onChangeText={t => {
          setEmail(t);
          setInvalid(null);
          setError(null);
        }}
        placeholder="name@university.ro"
        placeholderTextColor={colors.chalkFaint}
        style={inputStyle}
        value={email}
      />
      <Check
        label="I am 18 or older"
        value={adult}
        onChange={v => {
          setAdult(v);
          setInvalid(null);
        }}
      />
      <Check
        label="I accept the terms and privacy notice"
        value={terms}
        onChange={setTerms}
      />
      <ErrorText message={invalid ?? error} />
      <Button title="Send code" onPress={submit} busy={busy} wide />
      {DEV_SKIP_SIGN_IN && onDevSkipSignIn && (
        <NativeButton title="Skip sign-in (dev)" onPress={onDevSkipSignIn} />
      )}
      {__DEV__ && <FloorSensorsDebug />}
    </Screen>
  );
}

export function OtpScreen({ navigation, route }: Nav<'Otp'>) {
  const { email } = route.params;
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const verify = async () => {
    if (!OTP_RE.test(code)) {
      setError('Enter the 6 digits from the e-mail.');
      return;
    }
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const pair = await api('post', '/auth/verify', {
        body: {
          email,
          code,
          device: await getDeviceInfo(),
          accept_terms: true,
          confirm_adult: true,
        },
      });
      await saveTokens(pair);
      navigation.replace('Team');
    } catch (e) {
      setError(describeError(e, 'verify'));
      setBusy(false);
    }
  };

  const resend = async () => {
    setError(null);
    setNotice(null);
    try {
      await requestCode(email);
      setNotice('New code sent. Use the latest e-mail.');
    } catch (e) {
      setError(describeError(e, 'otp'));
    }
  };

  return (
    <Screen>
      <Heading>Enter the code</Heading>
      <Body>We sent a 6-digit code to {email}.</Body>
      <TextInput
        accessibilityLabel="6-digit code"
        autoComplete="sms-otp"
        keyboardType="number-pad"
        maxLength={6}
        onChangeText={t => {
          setCode(t.replace(/\D/g, ''));
          setError(null);
        }}
        placeholder="123456"
        placeholderTextColor={colors.chalkFaint}
        style={[inputStyle, styles.code]}
        value={code}
      />
      <ErrorText message={error} />
      {notice && <Body>{notice}</Body>}
      <Button title="Verify" onPress={verify} busy={busy} wide />
      <Button
        title="Send a new code"
        onPress={resend}
        disabled={busy}
        variant="text"
      />
    </Screen>
  );
}

type TeamData = { teams: Team[]; seasonId: number };

function isAlreadyJoined(e: unknown): boolean {
  return (
    e instanceof ApiError &&
    e.status === 409 &&
    (e.problem as { type?: string } | undefined)?.type ===
      'urn:floorwars:problem:already-joined'
  );
}

export function TeamScreen({ onDone }: { onDone: () => void }) {
  const [data, setData] = useState<TeamData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [joining, setJoining] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [teams, season] = await Promise.all([
        api('get', '/teams'),
        api('get', '/seasons/active'),
      ]);
      setData({ teams, seasonId: season.id });
    } catch (e) {
      setError(describeError(e, 'teams'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const pickedCode = data?.teams.find(t => t.id === selected)?.code;
  const join = async () => {
    if (!data || selected === null) {
      return;
    }
    setJoining(true);
    setError(null);
    try {
      await api('post', '/seasons/{id}/join', {
        path: { id: data.seasonId },
        body: { team_id: selected },
      });
    } catch (e) {
      // Only already-joined means there is nothing left to choose; season-not-active is a 409 too.
      if (!isAlreadyJoined(e)) {
        setError(describeError(e, 'join'));
        setJoining(false);
        return;
      }
    }
    await markTeamChosen(data.seasonId);
    onDone();
  };

  if (loading) {
    return (
      <Screen>
        <ActivityIndicator
          accessibilityLabel="Loading teams"
          color={colors.chalk}
        />
      </Screen>
    );
  }
  if (!data) {
    return (
      <Screen>
        <Heading>Pick your team</Heading>
        <ErrorText message={error} />
        <Button title="Try again" onPress={load} />
      </Screen>
    );
  }
  if (data.teams.length === 0) {
    return (
      <Screen>
        <Heading>Pick your team</Heading>
        <Body>No teams are set up yet. Check back soon.</Body>
        <Button title="Check again" onPress={load} variant="text" />
      </Screen>
    );
  }
  return (
    <Screen>
      <Heading>Pick your team</Heading>
      <Body>One team per season. You cannot change it later.</Body>
      <View style={styles.grid} accessibilityRole="radiogroup">
        {data.teams.map(t => {
          const { tone, ink } = teamTone(t.color_hex);
          const on = selected === t.id;
          return (
            <Pressable
              key={t.id}
              accessibilityRole="radio"
              accessibilityLabel={t.code}
              accessibilityState={{ selected: on }}
              onPress={() => setSelected(t.id)}
              style={[styles.tile, on && styles.tileOn]}
            >
              <View style={[styles.tileFill, { backgroundColor: tone }]}>
                <Text style={[styles.tileCode, { color: ink }]}>{t.code}</Text>
              </View>
            </Pressable>
          );
        })}
      </View>
      <ErrorText message={error} />
      <Button
        title={pickedCode ? `Join ${pickedCode}` : 'Pick a team'}
        onPress={join}
        busy={joining}
        disabled={selected === null}
        wide
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  check: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 48 },
  checkLabel: { ...type.body, flex: 1, color: colors.chalk },
  code: { fontSize: 28, letterSpacing: 8, fontVariant: ['tabular-nums'] },
  box: {
    width: 22,
    height: 22,
    borderRadius: 4,
    borderWidth: 2,
    borderColor: colors.edge,
    alignItems: 'center',
    justifyContent: 'center',
  },
  boxOn: { backgroundColor: colors.chalk, borderColor: colors.chalk },
  skyline: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'center',
    gap: 8,
  },
  wordmark: {
    fontFamily: fonts.display,
    fontSize: 52,
    lineHeight: 52,
    color: colors.chalk,
    marginTop: 12,
  },
  signTitle: { ...type.title, fontSize: 28, lineHeight: 30 },
  fieldLabel: {
    ...type.meta,
    fontFamily: fonts.semibold,
    color: colors.chalkDim,
    marginBottom: -10,
  },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
  tile: {
    width: '47%',
    flexGrow: 1,
    borderRadius: 11,
    borderWidth: 3,
    borderColor: 'transparent',
  },
  tileOn: { borderColor: colors.chalk },
  tileFill: {
    height: 106,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tileCode: { fontFamily: fonts.display, fontSize: 48, lineHeight: 52 },
});
