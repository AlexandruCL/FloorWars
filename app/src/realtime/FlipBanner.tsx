import { useEffect, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  PanResponder,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useReducedMotion } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '../api/client';
import { useMe } from '../data/myTeam';
import { useRead } from '../data/useRead';
import { colors, TeamTag, type } from '../ui/parts';
import { useGameEvents } from './useGameEvents';

const SHOW_MS = 5000;
const OUT = Easing.bezier(0.23, 1, 0.32, 1);

type Flip = {
  buildingId: number;
  to: string;
  from: string | null;
  key: number;
};

// "ETC took Faculty of …" when a building flips while the app is open (DESIGN.md section 8).
export function FlipBanner() {
  const navigation = useNavigation<any>();
  const { top } = useSafeAreaInsets();
  const reduce = useReducedMotion();
  const teams = useRead('teams', () => api('get', '/teams'));
  const buildings = useRead('buildings', () => api('get', '/buildings'));
  const mine = useMe().data?.team?.code ?? null;
  const [flip, setFlip] = useState<Flip | null>(null);
  const shown = useRef(new Animated.Value(0)).current;

  useGameEvents(e => {
    if (e.type === 'building_flipped') {
      setFlip({
        buildingId: e.building_id,
        to: e.to_team,
        from: e.from_team,
        key: Date.now(),
      });
    }
  });

  const hide = () =>
    Animated.timing(shown, {
      toValue: 0,
      duration: 160,
      easing: Easing.in(Easing.cubic),
      useNativeDriver: true,
    }).start(({ finished }) => finished && setFlip(null));

  useEffect(() => {
    if (!flip) {
      return;
    }
    shown.setValue(0);
    Animated.timing(shown, {
      toValue: 1,
      duration: 220,
      easing: OUT,
      useNativeDriver: true,
    }).start();
    const timer = setTimeout(hide, SHOW_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flip?.key]);

  // A fast upward flick dismisses it.
  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_e, g) => g.dy < -8,
      onPanResponderRelease: (_e, g) => {
        if (g.dy < -20 || g.vy < -0.5) {
          hide();
        }
      },
    }),
  ).current;

  if (!flip) {
    return null;
  }
  const name =
    buildings.data?.find(b => b.id === flip.buildingId)?.name ??
    `Building ${flip.buildingId}`;
  const color =
    teams.data?.find(t => t.code === flip.to)?.color_hex ?? colors.chalkFaint;
  const lost = !!mine && flip.from === mine && flip.to !== mine;
  const motion = reduce
    ? { opacity: shown }
    : {
        transform: [
          {
            translateY: shown.interpolate({
              inputRange: [0, 1],
              outputRange: [-160, 0],
            }),
          },
        ],
      };

  return (
    <Animated.View
      style={[styles.wrap, { top: top + 8 }, motion]}
      {...pan.panHandlers}
    >
      <Pressable
        accessibilityRole="button"
        accessibilityLiveRegion="polite"
        onPress={() => {
          hide();
          navigation.navigate('Main', {
            screen: 'Building',
            params: { buildingId: flip.buildingId },
          });
        }}
        style={styles.banner}
      >
        <TeamTag code={flip.to} color={color} size="medium" />
        <View style={styles.text}>
          <Text style={type.label}>{`${flip.to} took ${name}`}</Text>
          {lost && (
            <Text style={styles.sub}>
              Your team lost it. Tap to see the standings.
            </Text>
          )}
        </View>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: 'absolute', left: 12, right: 12 },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 12,
    borderRadius: 12,
    backgroundColor: colors.raised,
    borderWidth: 1,
    borderColor: colors.hairline,
  },
  text: { flex: 1, gap: 2 },
  sub: { ...type.meta, color: colors.chalkDim },
});
