import type { ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
} from 'react-native';

// Warm paper background, near-black ink tinted to match, one stair-sign orange accent.
export const colors = {
  paper: '#F6F2EC',
  ink: '#241E19',
  muted: '#625A52',
  line: '#CFC6BA',
  accent: '#B8430F',
  onAccent: '#FFFFFF',
  error: '#A31515',
};

export function Screen({ children }: { children: ReactNode }) {
  return (
    <ScrollView
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
        <ActivityIndicator
          color={secondary ? colors.accent : colors.onAccent}
        />
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
  borderColor: colors.line,
  borderRadius: 8,
  paddingHorizontal: 14,
  fontSize: 18,
  color: colors.ink,
  backgroundColor: '#FFFFFF',
} as const;

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.paper },
  content: { padding: 24, paddingTop: 32, gap: 16 },
  heading: { fontSize: 28, fontWeight: '700', color: colors.ink },
  body: { fontSize: 16, lineHeight: 24, color: colors.muted, maxWidth: 520 },
  error: { fontSize: 15, lineHeight: 22, color: colors.error },
  button: {
    minHeight: 52,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  buttonPrimary: { backgroundColor: colors.accent },
  buttonSecondary: { borderWidth: 1, borderColor: colors.accent },
  buttonOff: { opacity: 0.5 },
  buttonText: { fontSize: 17, fontWeight: '600', color: colors.onAccent },
  buttonTextSecondary: {
    fontSize: 17,
    fontWeight: '600',
    color: colors.accent,
  },
});
