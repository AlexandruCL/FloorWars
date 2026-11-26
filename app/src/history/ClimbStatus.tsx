import { StyleSheet, Text, View } from 'react-native';
import { Pictogram, type PictogramName } from '../ui/Pictogram';
import { colors, fonts } from '../ui/parts';
import type { SegmentRecord } from './today';

const STATUS: Record<
  SegmentRecord['status'],
  { word: string; icon: PictogramName; color: string }
> = {
  verified: { word: 'Counted', icon: 'check', color: colors.ok },
  pending: { word: 'Pending', icon: 'pending', color: colors.chalkDim },
  rejected: { word: 'Not counted', icon: 'cross', color: colors.bad },
};

// "86 steps, 12.4 m up"
export const climbDetail = (s: SegmentRecord) =>
  `${s.steps.toLocaleString('en-US')} steps, ${s.ascent_m.toFixed(1)} m up`;

// A climb's status as a pictogram and a word, so it never rests on colour alone.
export function ClimbStatus({ item }: { item: SegmentRecord }) {
  const s = STATUS[item.status];
  return (
    <View style={styles.status}>
      <Pictogram name={s.icon} size={16} color={s.color} />
      <Text style={[styles.word, { color: s.color }]}>{s.word}</Text>
    </View>
  );
}

export const statusWord = (item: SegmentRecord) => STATUS[item.status].word;

const styles = StyleSheet.create({
  status: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  word: { fontFamily: fonts.semibold, fontSize: 13, lineHeight: 18 },
});
