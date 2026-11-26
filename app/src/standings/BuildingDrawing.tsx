import { type ReactElement, useEffect, useRef } from 'react';
import { Animated, Easing, View } from 'react-native';
import { useReducedMotion } from 'react-native-reanimated';
import Svg, { G, Polygon, Rect, Text as SvgText } from 'react-native-svg';
import { colors, fonts } from '../ui/parts';
import { teamTone } from '../ui/tone';
import {
  allocateWindows,
  describeStandings,
  doorBay,
  facade,
  windowSlots,
} from './facade';

type Team = { code: string; color_hex: string; points: number };

// What the building looked like before, to replay the change floor by floor: a flip (the old
// standings) or a check-in (nothing lit). A new key starts the replay.
export type Replay = {
  kind: 'flip' | 'checkin';
  from: Team[];
  owner: string | null;
  key: number;
};

const AnimatedG = Animated.createAnimatedComponent(G);
// DESIGN.md section 11: flip 180 ms a floor, 40 ms apart; check-in 160 ms, 30 ms apart; ease-out.
const PACE = { flip: [180, 40], checkin: [160, 30] } as const;
const MAX_FLOORS = 8;

// One opacity per floor, so at most eight values animate, never one per window.
function useReplay(replay: Replay | null | undefined, floors: number) {
  const reduce = useReducedMotion();
  const ops = useRef(
    Array.from({ length: MAX_FLOORS }, () => new Animated.Value(1)),
  ).current;
  const flag = useRef(new Animated.Value(1)).current;
  const key = replay?.key;
  const kind = replay?.kind;
  useEffect(() => {
    if (key === undefined || !kind) {
      return;
    }
    const used = ops.slice(0, floors);
    [...used, flag].forEach(v => v.setValue(0));
    const ease = Easing.bezier(0.23, 1, 0.32, 1);
    const fade = (v: Animated.Value, duration: number) =>
      Animated.timing(v, {
        toValue: 1,
        duration,
        easing: ease,
        useNativeDriver: false,
      });
    // Reduced motion: one 150 ms crossfade for the whole building.
    const run = reduce
      ? Animated.parallel([...used, flag].map(v => fade(v, 150)))
      : Animated.parallel([
          Animated.stagger(
            PACE[kind][1],
            used.map(v => fade(v, PACE[kind][0])),
          ),
          Animated.sequence([
            Animated.delay(PACE[kind][1] * (floors - 1)),
            fade(flag, 200),
          ]),
        ]);
    run.start();
    return () => run.stop();
  }, [key, kind, floors, reduce, ops, flag]);
  return { ops, flag };
}

const WINDOW_RATIO = { tall: 0.78, square: 1, wide: 1.32 };
const WINDOW_SIZE = {
  tall: [0.44, 0.6],
  square: [0.5, 0.5],
  wide: [0.7, 0.42],
};
const ROOF_HEIGHT = { parapet: 0.14, stairL: 0.72, stairR: 0.72, gable: 0.85 };
const LABEL_GUTTER = 48;

// A building drawn from its id with its windows lit in team tones by share (DESIGN.md section 9).
// Large sizes add the owner's code on the flag and a code beside each team's band, so the
// drawing works without colour.
export function BuildingDrawing({
  buildingId,
  teams,
  owner,
  width,
  height,
  name,
  unlit = false,
  replay,
}: {
  buildingId: number;
  teams: Team[];
  owner: string | null;
  width: number;
  height: number;
  name?: string;
  unlit?: boolean;
  replay?: Replay | null;
}) {
  const f = facade(buildingId);
  const large = width >= 160;
  const pole = large ? 22 : Math.max(5, Math.round(height * 0.08));
  const flagH = large ? 15 : Math.max(3, Math.round(height * 0.06));
  // Room for band codes on the right only when windows are lit.
  const labelled = large && !unlit && teams.some(t => t.points > 0);
  const availW = width - (labelled ? LABEL_GUTTER : 0);
  const ratio = WINDOW_RATIO[f.windows];
  const fh = Math.max(
    3,
    Math.min(
      (height - 4 - pole) / (f.floors + ROOF_HEIGHT[f.roof]),
      (availW * 0.92) / (f.bays * ratio),
    ),
  );
  const bw = fh * ratio;
  const fw = f.bays * bw;
  const fht = f.floors * fh;
  const fx = (availW - fw) / 2;
  const fy = height - 1 - fht;

  const roof: ReactElement[] = [];
  let poleX = fx + fw * 0.72;
  let base = fy - fh * 0.14;
  if (f.roof === 'parapet') {
    roof.push(
      <Rect
        key="p"
        x={fx - 2}
        y={base}
        width={fw + 4}
        height={fh * 0.14}
        fill={colors.facadeLight}
      />,
    );
  } else if (f.roof === 'gable') {
    const top = fy - fh * 0.85;
    roof.push(
      <Polygon
        key="g"
        points={`${fx - 3},${fy} ${fx + fw / 2},${top} ${fx + fw + 3},${fy}`}
        fill={colors.facadeLight}
      />,
      <Polygon
        key="gi"
        points={`${fx},${fy} ${fx + fw / 2},${top + 3} ${fx + fw},${fy}`}
        fill={colors.facade}
      />,
    );
    poleX = fx + fw / 2 - 1;
    base = top;
  } else {
    const hw = bw * 1.1;
    const hh = fh * 0.72;
    const hx = f.roof === 'stairL' ? fx + bw * 0.3 : fx + fw - bw * 0.3 - hw;
    roof.push(
      <Rect
        key="e"
        x={fx - 1}
        y={fy - 2}
        width={fw + 2}
        height={2}
        fill={colors.facadeLight}
      />,
      <Rect
        key="h"
        x={hx}
        y={fy - hh}
        width={hw}
        height={hh}
        fill={colors.facade}
      />,
      <Rect
        key="he"
        x={hx - 1}
        y={fy - hh - 2}
        width={hw + 2}
        height={2}
        fill={colors.facadeLight}
      />,
    );
    poleX = hx + hw / 2 - 1;
    base = fy - hh - 2;
  }

  const slots = windowSlots(f);
  const lit = unlit ? [] : allocateWindows(teams, slots.length, owner);
  const before = replay
    ? allocateWindows(replay.from, slots.length, replay.owner)
    : lit;
  const tone = new Map(
    [...(replay?.from ?? []), ...teams].map(t => [
      t.code,
      teamTone(t.color_hex),
    ]),
  );
  const { ops, flag } = useReplay(replay, f.floors);
  const [sw, sh] = WINDOW_SIZE[f.windows];
  const ww = bw * sw;
  const wh = fh * sh;
  const rowY = (floor: number) => fy + (f.floors - 1 - floor) * fh;

  const ownerTeam = unlit
    ? undefined
    : teams.find(t => t.code === owner && t.points > 0);
  const ownerTone = ownerTeam && tone.get(ownerTeam.code);
  const flagW =
    large && ownerTeam
      ? Math.max(22, ownerTeam.code.length * 7 + 8)
      : Math.max(5, bw * 0.55);

  // One code per team at the middle of its band; a label that would overlap the one below drops.
  const bands: { code: string; color: string; y: number }[] = [];
  if (large) {
    const rows = new Map<string, number[]>();
    lit.forEach((t, i) => {
      const r = rows.get(t.code) ?? [];
      if (!r.includes(slots[i].floor)) {
        r.push(slots[i].floor);
      }
      rows.set(t.code, r);
    });
    let last = Infinity;
    [...rows.entries()]
      .map(([code, r]) => ({
        code,
        color: tone.get(code)!.tone,
        y: r.reduce((s, fl) => s + rowY(fl) + fh / 2, 0) / r.length,
      }))
      .sort((a, b) => b.y - a.y)
      .forEach(b => {
        if (last - b.y >= 17) {
          bands.push(b);
          last = b.y;
        }
      });
  }

  const windowRect = (
    s: { floor: number; bay: number },
    i: number,
    t: Team | undefined,
  ) => (
    <Rect
      key={i}
      x={fx + s.bay * bw + (bw - ww) / 2}
      y={rowY(s.floor) + (fh - wh) / 2}
      width={ww}
      height={wh}
      rx={large ? 1.5 : 0.5}
      fill={t ? tone.get(t.code)!.tone : colors.window}
    />
  );

  const label = `${name ? `${name}. ` : ''}${
    unlit ? describeStandings([], null) : describeStandings(teams, owner)
  }`;
  return (
    <View accessible accessibilityRole="image" accessibilityLabel={label}>
      <Svg width={width} height={height}>
        <Rect
          x={0}
          y={height - 1}
          width={width}
          height={1}
          fill={colors.hairline}
        />
        <Rect x={fx} y={fy} width={fw} height={fht} fill={colors.facade} />
        {roof}
        <Rect
          x={fx + doorBay(f) * bw + (bw - bw * 0.42) / 2}
          y={fy + fht - fh * 0.74}
          width={bw * 0.42}
          height={fh * 0.74}
          fill={colors.facadeLight}
        />
        {slots.map((s, i) => windowRect(s, i, before[i]))}
        {/* The new windows, one group per floor, fade in over the old ones from the ground up. */}
        {replay &&
          Array.from({ length: f.floors }, (_, floor) => (
            <AnimatedG key={`f${floor}`} opacity={ops[floor]}>
              {slots.map(
                (s, i) => s.floor === floor && windowRect(s, i, lit[i]),
              )}
            </AnimatedG>
          ))}
        {ownerTone && (
          <AnimatedG opacity={replay ? flag : 1}>
            <Rect
              x={poleX}
              y={base - pole}
              width={2}
              height={pole}
              fill={colors.chalkFaint}
            />
            <Rect
              x={poleX + 2}
              y={base - pole}
              width={flagW}
              height={flagH}
              fill={ownerTone.tone}
            />
            {large && (
              <SvgText
                x={poleX + 2 + flagW / 2}
                y={base - pole + flagH - 3}
                fontFamily={fonts.display}
                fontSize={12}
                fill={ownerTone.ink}
                textAnchor="middle"
              >
                {ownerTeam!.code}
              </SvgText>
            )}
          </AnimatedG>
        )}
        {bands.map(b => (
          <SvgText
            key={b.code}
            x={fx + fw + 15}
            y={b.y + 5}
            fontFamily={fonts.display}
            fontSize={15}
            fill={b.color}
          >
            {b.code}
          </SvgText>
        ))}
        {bands.map(b => (
          <Rect
            key={`t${b.code}`}
            x={fx + fw + 4}
            y={b.y}
            width={8}
            height={1}
            fill={b.color}
          />
        ))}
      </Svg>
    </View>
  );
}
