import { useEffect, useRef, useState } from 'react';
import {
  PermissionsAndroid,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import Share from 'react-native-share';
import { FloorSensors, requestPermissions } from '../native/floorSensors';

export const LABELS = [
  'stairs_up',
  'stairs_down',
  'elevator_up',
  'walk_flat',
  'shake',
  'blow',
];
export const PLACEMENTS = ['pocket', 'hand', 'bag'];

function formatElapsed(ms: number) {
  const seconds = Math.floor(ms / 1000);
  const mm = String(Math.floor(seconds / 60)).padStart(2, '0');
  const ss = String(seconds % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

function Choice({
  title,
  options,
  value,
  onChange,
  disabled,
}: {
  title: string;
  options: string[];
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  return (
    <View style={styles.group} accessibilityRole="radiogroup">
      <Text style={styles.groupTitle}>{title}</Text>
      <View style={styles.choices}>
        {options.map(option => {
          const selected = option === value;
          return (
            <Pressable
              key={option}
              accessibilityRole="radio"
              accessibilityState={{ checked: selected, disabled }}
              disabled={disabled}
              onPress={() => onChange(option)}
              style={[
                styles.choice,
                selected && styles.choiceSelected,
                disabled && !selected && styles.choiceDisabled,
              ]}
            >
              <Text style={selected ? styles.choiceTextSelected : styles.text}>
                {option}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export function SensorLoggerScreen() {
  const [label, setLabel] = useState(LABELS[0]);
  const [placement, setPlacement] = useState(PLACEMENTS[0]);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const [saving, setSaving] = useState(false);
  const [savedPath, setSavedPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Placement to save with once the service reports it has stopped.
  const saveOnStop = useRef<string | null>(null);

  useEffect(() => {
    const subscription = FloorSensors.onStatusChange(async event => {
      if (event.logging) {
        const t = Date.now();
        setNow(t);
        setStartedAt(t);
        return;
      }
      setStartedAt(null);
      const pending = saveOnStop.current;
      if (pending === null) {
        return;
      }
      saveOnStop.current = null;
      try {
        setSavedPath(await FloorSensors.saveTrace(pending));
      } catch (e) {
        setError(`Could not save the trace: ${String(e)}`);
      } finally {
        setSaving(false);
      }
    });
    return () => subscription.remove();
  }, []);

  useEffect(() => {
    if (startedAt === null) {
      return;
    }
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, [startedAt]);

  const recording = startedAt !== null;

  const onStart = async () => {
    setError(null);
    setSavedPath(null);
    const permissions = await requestPermissions();
    if (
      permissions[PermissionsAndroid.PERMISSIONS.ACTIVITY_RECOGNITION] !==
      'granted'
    ) {
      setError(
        'Physical activity permission is needed to record. Allow it in Settings, then try again.',
      );
      return;
    }
    FloorSensors.startLogging(label);
  };

  const onStop = () => {
    saveOnStop.current = placement;
    setSaving(true);
    FloorSensors.stopLogging();
  };

  const onShare = async () => {
    if (savedPath === null) {
      return;
    }
    try {
      await Share.open({
        url: `file://${savedPath}`,
        type: 'text/csv',
        failOnCancel: false,
      });
    } catch (e) {
      setError(`Could not open the share sheet: ${String(e)}`);
    }
  };

  let statusLine = 'Pick a label and placement, then start recording.';
  if (recording) {
    statusLine = `Recording ${label}, ${placement}`;
  } else if (saving) {
    statusLine = 'Saving the trace...';
  } else if (savedPath !== null) {
    statusLine = `Saved ${savedPath.split('/').pop()}`;
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Choice
        title="Label"
        options={LABELS}
        value={label}
        onChange={setLabel}
        disabled={recording || saving}
      />
      <Choice
        title="Placement"
        options={PLACEMENTS}
        value={placement}
        onChange={setPlacement}
        disabled={recording || saving}
      />

      <Text style={styles.timer} accessibilityLabel="Elapsed time">
        {formatElapsed(recording ? now - startedAt : 0)}
      </Text>
      <Text style={styles.text}>{statusLine}</Text>

      <Pressable
        accessibilityRole="button"
        disabled={saving}
        onPress={recording ? onStop : onStart}
        style={[styles.primary, recording && styles.stop]}
      >
        <Text style={styles.primaryText}>
          {recording ? 'Stop and save' : 'Start recording'}
        </Text>
      </Pressable>

      {savedPath !== null && !recording && (
        <Pressable
          accessibilityRole="button"
          onPress={onShare}
          style={styles.secondary}
        >
          <Text style={styles.text}>Share CSV</Text>
        </Pressable>
      )}

      {error !== null && <Text style={styles.error}>{error}</Text>}
    </ScrollView>
  );
}

const ink = '#1b1f24';

const styles = StyleSheet.create({
  screen: { backgroundColor: '#ffffff' },
  content: { padding: 16, gap: 16 },
  group: { gap: 8 },
  groupTitle: { color: ink, fontSize: 16, fontWeight: '600' },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  choice: {
    minHeight: 44,
    paddingHorizontal: 14,
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#8a939e',
    borderRadius: 8,
  },
  choiceSelected: { backgroundColor: ink, borderColor: ink },
  choiceDisabled: { opacity: 0.5 },
  choiceTextSelected: { color: '#ffffff', fontSize: 15 },
  text: { color: ink, fontSize: 15 },
  timer: {
    color: ink,
    fontSize: 56,
    fontWeight: '300',
    fontVariant: ['tabular-nums'],
    textAlign: 'center',
    marginTop: 8,
  },
  primary: {
    minHeight: 52,
    borderRadius: 8,
    backgroundColor: ink,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // Red marks the live recording state; nothing else on the screen uses it.
  stop: { backgroundColor: '#b3261e' },
  primaryText: { color: '#ffffff', fontSize: 17, fontWeight: '600' },
  secondary: {
    minHeight: 48,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: ink,
    alignItems: 'center',
    justifyContent: 'center',
  },
  error: { color: '#b3261e', fontSize: 15 },
});
