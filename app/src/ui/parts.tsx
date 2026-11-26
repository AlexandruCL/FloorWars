import type { ReactElement, ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  type RefreshControlProps,
  ScrollView,
  StyleSheet,
  Text,
} from 'react-native';

// Night palette (DESIGN.md section 5). Colour belongs to the teams; the chrome is night neutrals and chalk.
export const colors = {
  night: '#0A0E16',
  raised: '#141A24',
  sunken: '#202732',
  hairline: '#2D333E',
  edge: '#666C78',
  chalk: '#EEF0F4',
  chalkDim: '#B4BBC6',
  chalkFaint: '#8D94A0',
  facade: '#1C2330',
  facadeLight: '#29313E',
  window: '#11161F',
  ok: '#61DA92',
  warn: '#F8C655',
  bad: '#F9786A',
};

// Android loads each file in android/app/src/main/assets/fonts by its name; never add fontWeight
// next to these, or Android fakes a bolder cut.
export const fonts = {
  stencil: 'BigShouldersStencilDisplay-Black',
  display: 'BigShouldersDisplay-ExtraBold',
  regular: 'Barlow-Regular',
  medium: 'Barlow-Medium',
  semibold: 'Barlow-SemiBold',
};

// Type roles (DESIGN.md section 6).
export const type = StyleSheet.create({
  display: {
    fontFamily: fonts.stencil,
    fontSize: 64,
    lineHeight: 60,
    color: colors.chalk,
  },
  title: {
    fontFamily: fonts.display,
    fontSize: 34,
    lineHeight: 36,
    color: colors.chalk,
  },
  heading: {
    fontFamily: fonts.display,
    fontSize: 24,
    lineHeight: 28,
    color: colors.chalk,
  },
  body: {
    fontFamily: fonts.regular,
    fontSize: 16,
    lineHeight: 25,
    color: colors.chalkDim,
  },
  label: {
    fontFamily: fonts.semibold,
    fontSize: 16,
    lineHeight: 22,
    color: colors.chalk,
  },
  meta: {
    fontFamily: fonts.medium,
    fontSize: 13,
    lineHeight: 18,
    color: colors.chalkFaint,
  },
});

export function Screen({
  children,
  refreshControl,
}: {
  children: ReactNode;
  refreshControl?: ReactElement<RefreshControlProps>;
}) {
  return (
    <ScrollView
      refreshControl={refreshControl}
      style={styles.screen}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      {children}
    </ScrollView>
  );
}

export function Heading({ children }: { children: string }) {
  return (
    <Text accessibilityRole="header" style={styles.heading}>
      {children}
    </Text>
  );
}

export function Body({ children }: { children: ReactNode }) {
  return <Text style={styles.body}>{children}</Text>;
}

export function ErrorText({ message }: { message: string | null }) {
  return message ? (
    <Text accessibilityLiveRegion="polite" style={styles.error}>
      {message}
    </Text>
  ) : null;
}

export function Button({
  title,
  onPress,
  busy,
  disabled,
  secondary,
}: {
  title: string;
  onPress: () => void;
  busy?: boolean;
  disabled?: boolean;
  secondary?: boolean;
}) {
  const off = disabled || busy;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!off, busy: !!busy }}
      disabled={off}
      onPress={onPress}
      style={[
        styles.button,
        secondary ? styles.buttonSecondary : styles.buttonPrimary,
        off && styles.buttonOff,
      ]}
    >
      {busy ? (
        <ActivityIndicator color={secondary ? colors.chalk : colors.night} />
      ) : (
        <Text
          style={secondary ? styles.buttonTextSecondary : styles.buttonText}
        >
          {title}
        </Text>
      )}
    </Pressable>
  );
}

export const inputStyle = {
  minHeight: 52,
  borderWidth: 1,
  borderColor: colors.edge,
  borderRadius: 12,
  paddingHorizontal: 14,
  fontFamily: fonts.medium,
  fontSize: 18,
  color: colors.chalk,
  backgroundColor: colors.sunken,
} as const;

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.night },
  content: { padding: 16, paddingTop: 24, gap: 16 },
  heading: type.title,
  body: { ...type.body, maxWidth: 520 },
  error: { ...type.body, color: colors.bad },
  button: {
    minHeight: 48,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
  },
  buttonPrimary: { backgroundColor: colors.chalk },
  buttonSecondary: { borderWidth: 1, borderColor: colors.edge },
  buttonOff: { opacity: 0.5 },
  buttonText: { ...type.label, color: colors.night },
  buttonTextSecondary: type.label,
});
