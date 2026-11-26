import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  SectionList,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { api } from '../api/client';
import { clock, MESSAGES, ReadState, useRead } from '../data/useRead';
import { ClimbStatus, climbDetail, statusWord } from '../history/ClimbStatus';
import { reasonText } from '../history/reasons';
import {
  fetchSegmentPage,
  localMidnight,
  type SegmentRecord,
} from '../history/today';
import { Body, colors, type } from '../ui/parts';

// "Today", "Yesterday", else "Monday 23 November".
export function dayLabel(ms: number, now = Date.now()): string {
  const day = localMidnight(ms);
  const today = localMidnight(now);
  if (day === today) {
    return 'Today';
  }
  if (day === localMidnight(today - 1)) {
    return 'Yesterday';
  }
  return new Date(ms).toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
}

function Row({ item, building }: { item: SegmentRecord; building: string }) {
  const at = clock(Date.parse(item.started_at));
  const fewer =
    item.status === 'verified' && item.steps_scored < item.steps
      ? `${item.steps_scored.toLocaleString('en-US')} steps scored`
      : null;
  const reason = item.status === 'rejected' ? reasonText(item.reason) : null;
  return (
    <View
      style={styles.row}
      accessible
      accessibilityLabel={[
        at,
        building,
        climbDetail(item),
        statusWord(item),
        fewer,
        reason,
      ]
        .filter(Boolean)
        .join(', ')}
    >
      <Text style={styles.time}>{at}</Text>
      <View style={styles.body}>
        <Text style={type.label}>{building}</Text>
        <Text style={styles.sub}>{climbDetail(item)}</Text>
        <View style={styles.statusLine}>
          <ClimbStatus item={item} />
          {fewer && <Text style={styles.sub}>{fewer}</Text>}
        </View>
        {reason && <Text style={styles.reason}>{reason}</Text>}
      </View>
    </View>
  );
}

export function HistoryScreen() {
  const first = useRead('history:first', () => fetchSegmentPage());
  const buildings = useRead('buildings', () => api('get', '/buildings'));
  const [more, setMore] = useState<{
    items: SegmentRecord[];
    cursor: string | null | undefined; // undefined: follow the first page
    failed: boolean;
    busy: boolean;
  }>({ items: [], cursor: undefined, failed: false, busy: false });

  const cursor =
    more.cursor === undefined ? first.data?.next_cursor : more.cursor;
  const loadMore = useCallback(async () => {
    if (!cursor || more.busy || more.failed) {
      return;
    }
    setMore(m => ({ ...m, busy: true }));
    try {
      const page = await fetchSegmentPage(cursor);
      setMore(m => ({
        items: [...m.items, ...page.items],
        cursor: page.next_cursor,
        failed: false,
        busy: false,
      }));
    } catch {
      setMore(m => ({ ...m, failed: true, busy: false }));
    }
  }, [cursor, more.busy, more.failed]);

  const refresh = () => {
    setMore({ items: [], cursor: undefined, failed: false, busy: false });
    first.refresh();
  };
  const items = [...(first.data?.items ?? []), ...more.items];
  const sections: { title: string; data: SegmentRecord[] }[] = [];
  for (const item of items) {
    const title = dayLabel(Date.parse(item.started_at));
    const last = sections[sections.length - 1];
    if (last?.title === title) {
      last.data.push(item);
    } else {
      sections.push({ title, data: [item] });
    }
  }
  const nameOf = (id: number) =>
    buildings.data?.find(b => b.id === id)?.name ?? `Building ${id}`;

  return (
    <SectionList
      testID="history-list"
      style={styles.list}
      contentContainerStyle={styles.content}
      sections={sections}
      stickySectionHeadersEnabled
      renderSectionHeader={({ section }) => (
        <Text style={styles.day} accessibilityRole="header">
          {section.title}
        </Text>
      )}
      keyExtractor={s => s.id}
      renderItem={({ item }) => (
        <Row item={item} building={nameOf(item.building_id)} />
      )}
      onEndReached={loadMore}
      onEndReachedThreshold={0.5}
      refreshControl={
        <RefreshControl refreshing={first.refreshing} onRefresh={refresh} />
      }
      ListHeaderComponent={
        <View style={styles.head}>
          <ReadState read={first} />
        </View>
      }
      ListEmptyComponent={
        first.data ? (
          <Body>
            No climbs yet. Check in at a building and take the stairs.
          </Body>
        ) : undefined
      }
      ListFooterComponent={
        more.busy ? (
          <ActivityIndicator color={colors.chalk} />
        ) : more.failed ? (
          <Text style={styles.reason}>{MESSAGES.error}</Text>
        ) : undefined
      }
    />
  );
}

const styles = StyleSheet.create({
  list: { flex: 1, backgroundColor: colors.night },
  content: { paddingHorizontal: 16, paddingBottom: 24 },
  head: { gap: 16 },
  day: {
    ...type.meta,
    color: colors.chalkDim,
    paddingTop: 16,
    paddingBottom: 6,
    backgroundColor: colors.night,
  },
  row: {
    flexDirection: 'row',
    gap: 12,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.hairline,
  },
  time: { ...type.label, width: 56, fontVariant: ['tabular-nums'] },
  body: { flex: 1, gap: 2 },
  sub: { ...type.meta, color: colors.chalkDim },
  statusLine: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  reason: { ...type.body, fontSize: 15, lineHeight: 22 },
});
