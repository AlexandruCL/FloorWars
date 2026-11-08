import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  Button as NativeButton,
  Pressable,
  Switch,
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
import {
  Body,
  Button,
  colors,
  ErrorText,
  Heading,
  inputStyle,
  Screen,
} from '../ui/parts';

type Team = components['schemas']['Team'];
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
    <View style={styles.check}>
      <Switch
        accessibilityLabel={label}
        value={value}
        onValueChange={onChange}
        trackColor={{ true: colors.accent, false: colors.line }}
      />
      <Text style={styles.checkLabel}>{label}</Text>
    </View>
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
      <Heading>Climb for your faculty</Heading>
      <Body>Enter your university e-mail. We send you a 6-digit code.</Body>
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
        placeholderTextColor={colors.muted}
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
      <Button title="Send code" onPress={submit} busy={busy} />
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
        placeholderTextColor={colors.muted}
        style={[inputStyle, styles.code]}
        value={code}
      />
      <ErrorText message={error} />
      {notice && <Body>{notice}</Body>}
      <Button title="Verify" onPress={verify} busy={busy} />
      <Button
        title="Send a new code"
        onPress={resend}
        disabled={busy}
        secondary
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
          color={colors.accent}
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
        <Button title="Check again" onPress={load} secondary />
      </Screen>
    );
  }
  return (
    <Screen>
      <Heading>Pick your team</Heading>
      <Body>One team per season. You cannot change it later.</Body>
      {data.teams.map(t => (
        <Pressable
          key={t.id}
          accessibilityRole="radio"
          accessibilityState={{ selected: selected === t.id }}
          onPress={() => setSelected(t.id)}
          style={[styles.team, selected === t.id && styles.teamSelected]}
        >
          <View style={[styles.swatch, { backgroundColor: t.color_hex }]} />
          <Text style={styles.teamCode}>{t.code}</Text>
        </Pressable>
      ))}
      <ErrorText message={error} />
      <Button
        title="Join team"
        onPress={join}
        busy={joining}
        disabled={selected === null}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  check: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 48 },
  checkLabel: { flex: 1, fontSize: 16, color: colors.ink },
  code: { fontSize: 28, letterSpacing: 8 },
  team: {
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    paddingHorizontal: 14,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: '#FFFFFF',
  },
  teamSelected: { borderWidth: 2, borderColor: colors.accent },
  swatch: { width: 24, height: 24, borderRadius: 12 },
  teamCode: { fontSize: 18, fontWeight: '600', color: colors.ink },
});
