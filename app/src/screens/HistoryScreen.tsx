import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { api } from '../api/client';
import { MESSAGES, ReadState, useRead } from '../data/useRead';
import { reasonText } from '../history/reasons';
import { fetchSegmentPage, type SegmentRecord } from '../history/today';
import { Body, colors, Heading } from '../ui/parts';

const STATUS = {
  verified: 'Verified',
  pending: 'Pending',
  rejected: 'Rejected',
};

function Row({ item, building }: { item: SegmentRecord; building: string }) {
  const when = new Date(item.started_at).toLocaleString([], {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
  return (
    <View style={styles.row} accessible>
      <Text style={styles.when}>{when}</Text>
      <Text style={styles.building}>{building}</Text>
      <Text style={styles.detail}>
        {`${item.steps} steps, ${item.ascent_m} m`}
      </Text>
      <Text style={styles.detail}>
        {item.status === 'verified'
          ? `${STATUS.verified}, ${item.steps_scored} steps scored`
          : STATUS[item.status]}
      </Text>
      {item.status === 'rejected' && (
        <Text style={styles.reason}>{reasonText(item.reason)}</Text>
      )}
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
  const nameOf = (id: number) =>
    buildings.data?.find(b => b.id === id)?.name ?? `Building ${id}`;

  return (
    <FlatList
      testID="history-list"
      style={styles.list}
      contentContainerStyle={styles.content}
      data={items}
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
          <Heading>Climb history</Heading>
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
          <ActivityIndicator color={colors.accent} />
        ) : more.failed ? (
          <Text style={styles.reason}>{MESSAGES.error}</Text>
        ) : undefined
      }
    />
  );
}

const styles = StyleSheet.create({
  list: { flex: 1, backgroundColor: colors.paper },
  content: { padding: 24, paddingTop: 32, gap: 0 },
  head: { gap: 16, marginBottom: 8 },
  row: {
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
    gap: 2,
  },
  when: { fontSize: 14, color: colors.muted },
  building: { fontSize: 18, fontWeight: '600', color: colors.ink },
  detail: { fontSize: 16, color: colors.ink },
  reason: { fontSize: 15, lineHeight: 22, color: colors.muted },
});
