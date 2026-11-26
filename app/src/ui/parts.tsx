import {
  Children,
  createContext,
  type ReactElement,
  type ReactNode,
  useContext,
} from 'react';
import {
  ActivityIndicator,
  Pressable,
  type RefreshControlProps,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { HeaderShownContext } from '@react-navigation/elements';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Pictogram } from './Pictogram';
import { teamTone, type Tone } from './tone';

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
  // Tab screens have no header above them, so they clear the status bar themselves.
  const underHeader = useContext(HeaderShownContext);
  const { top } = useSafeAreaInsets();
  return (
    <ScrollView
      refreshControl={refreshControl}
      style={styles.screen}
      contentContainerStyle={[
        styles.content,
        !underHeader && { paddingTop: styles.content.paddingTop + top },
      ]}
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

// Your team's tone, the app's only accent (DESIGN.md section 5). Null before a team is known: chalk.
export const AccentContext = createContext<Tone | null>(null);

// primary: the one filled action per screen. text: every other action. danger: Sign out.
export function Button({
  title,
  onPress,
  busy,
  disabled,
  variant = 'primary',
  wide,
}: {
  title: string;
  onPress: () => void;
  busy?: boolean;
  disabled?: boolean;
  variant?: 'primary' | 'text' | 'danger';
  // Full width at the end of a form or in a sticky bar; otherwise as wide as its label.
  wide?: boolean;
}) {
  const accent = useContext(AccentContext);
  const off = disabled || busy;
  const primary = variant === 'primary';
  const fill = primary
    ? off && !busy
      ? colors.sunken
      : accent?.tone ?? colors.chalk
    : undefined;
  const ink = disabled
    ? colors.chalkFaint
    : primary
    ? accent?.ink ?? colors.night
    : variant === 'danger'
    ? colors.bad
    : colors.chalk;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      accessibilityState={{ disabled: !!off, busy: !!busy }}
      disabled={off}
      onPress={onPress}
      style={[
        primary ? styles.primary : styles.textButton,
        wide && styles.wide,
        fill !== undefined && { backgroundColor: fill },
      ]}
    >
      {/* The label keeps its width while the spinner shows, so the button does not jump. */}
      <Text style={[type.label, { color: ink }, busy && styles.hidden]}>
        {title}
      </Text>
      {busy && <ActivityIndicator style={styles.spinner} color={ink} />}
    </Pressable>
  );
}

// A navigation or settings row: title, optional subline and value, chevron when it opens something.
export function Row({
  title,
  subline,
  value,
  onPress,
  danger,
}: {
  title: string;
  subline?: string;
  value?: string;
  onPress?: () => void;
  danger?: boolean;
}) {
  const body = (
    <>
      <View style={styles.rowText}>
        <Text style={[type.label, danger && { color: colors.bad }]}>
          {title}
        </Text>
        {subline ? <Text style={styles.subline}>{subline}</Text> : null}
      </View>
      {value ? <Text style={styles.rowValue}>{value}</Text> : null}
      {onPress && !danger ? (
        <Pictogram name="chevron" size={20} color={colors.chalkFaint} />
      ) : null}
    </>
  );
  return onPress ? (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
    >
      {body}
    </Pressable>
  ) : (
    <View style={styles.row}>{body}</View>
  );
}

// Rows on one raised surface with inset hairlines, so a list never becomes a stack of boxes.
export function RowGroup({ children }: { children: ReactNode }) {
  const rows = Children.toArray(children);
  return (
    <View style={styles.group}>
      {rows.map((row, i) => (
        <View key={i}>
          {i > 0 && <View style={styles.inset} />}
          {row}
        </View>
      ))}
    </View>
  );
}

const tagSizes = {
  small: { fontSize: 16, height: 24, paddingHorizontal: 6, borderRadius: 4 },
  medium: { fontSize: 20, height: 32, paddingHorizontal: 8, borderRadius: 4 },
  jersey: {
    fontSize: 48,
    height: 72,
    minWidth: 72,
    paddingHorizontal: 8,
    borderRadius: 8,
  },
};

// The team code on its tone. Colour is never alone: the code is always written.
export function TeamTag({
  code,
  color,
  size = 'small',
}: {
  code: string;
  color: string;
  size?: keyof typeof tagSizes;
}) {
  const { tone, ink } = teamTone(color);
  const { fontSize, ...box } = tagSizes[size];
  return (
    <View style={[styles.tag, box, { backgroundColor: tone }]}>
      <Text
        style={{
          fontFamily: fonts.display,
          fontSize,
          lineHeight: box.height,
          color: ink,
        }}
      >
        {code}
      </Text>
    </View>
  );
}

// A status that needs the player: one sentence and the action that fixes it.
export function Notice({
  kind = 'warn',
  message,
  action,
}: {
  kind?: 'warn' | 'bad';
  message: string;
  action?: { title: string; onPress: () => void };
}) {
  return (
    <View style={styles.notice} accessibilityLiveRegion="polite">
      <View style={styles.noticeIcon}>
        <Pictogram name="alert" size={20} color={colors[kind]} />
      </View>
      <View style={styles.noticeBody}>
        <Text style={styles.noticeText}>{message}</Text>
        {action ? (
          <Pressable
            accessibilityRole="button"
            onPress={action.onPress}
            style={styles.noticeAction}
          >
            <Text style={type.label}>{action.title}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
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
  primary: {
    minHeight: 48,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
    alignSelf: 'flex-start',
  },
  textButton: {
    minHeight: 48,
    justifyContent: 'center',
    paddingHorizontal: 12,
    alignSelf: 'flex-start',
  },
  wide: { alignSelf: 'stretch', alignItems: 'center' },
  hidden: { opacity: 0 },
  spinner: { position: 'absolute' },
  row: {
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingLeft: 16,
    paddingRight: 12,
    paddingVertical: 8,
  },
  rowPressed: { backgroundColor: colors.sunken },
  rowText: { flex: 1, gap: 2 },
  subline: { ...type.meta, color: colors.chalkDim },
  rowValue: {
    fontFamily: fonts.medium,
    fontSize: 16,
    lineHeight: 22,
    color: colors.chalkDim,
  },
  group: {
    backgroundColor: colors.raised,
    borderRadius: 12,
    overflow: 'hidden',
  },
  inset: {
    height: StyleSheet.hairlineWidth,
    marginLeft: 16,
    backgroundColor: colors.hairline,
  },
  tag: {
    alignSelf: 'flex-start',
    justifyContent: 'center',
    alignItems: 'center',
  },
  notice: {
    flexDirection: 'row',
    gap: 12,
    paddingTop: 12,
    paddingRight: 12,
    paddingLeft: 14,
    paddingBottom: 4,
    borderRadius: 12,
    backgroundColor: colors.raised,
  },
  noticeIcon: { paddingTop: 1 },
  noticeBody: { flex: 1, alignItems: 'flex-start' },
  noticeText: {
    fontFamily: fonts.regular,
    fontSize: 15,
    lineHeight: 22,
    color: colors.chalk,
  },
  noticeAction: { minHeight: 48, justifyContent: 'center' },
});
