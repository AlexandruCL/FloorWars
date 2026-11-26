import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshControl, StyleSheet, Text, View } from 'react-native';
import { ActivityIndicator } from 'react-native';
import { ApiError } from '../api/client';
import { colors, type } from '../ui/parts';

// Reads are cached in memory per key and lost on app restart (Cristea's decision, 2026-11-17).
const cache = new Map<string, { value: unknown; at: number }>();
export function clearReadCache() {
  cache.clear();
}

export type ReadFailure = 'offline' | 'notfound' | 'error';

export function failureOf(e: unknown): ReadFailure {
  if (e instanceof ApiError) {
    return e.status === 404 ? 'notfound' : 'error';
  }
  return 'offline'; // fetch rejected: no answer from the server
}

export type Read<T> = {
  data: T | null;
  loading: boolean;
  failure: ReadFailure | null; // set when the last attempt failed
  cachedAt: number | null; // set when data is a cached copy shown after a failure
  refreshing: boolean;
  refresh: () => void;
};

// key null: nothing to read yet.
export function useRead<T>(key: string | null, fetcher: () => Promise<T>) {
  const fetchRef = useRef(fetcher);
  fetchRef.current = fetcher;
  const [state, setState] = useState<Omit<Read<T>, 'refresh' | 'refreshing'>>({
    data: null,
    loading: true,
    failure: null,
    cachedAt: null,
  });
  const [refreshing, setRefreshing] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (key === null) {
      return undefined;
    }
    let live = true;
    const hit = cache.get(key);
    setState({
      data: (hit?.value as T | undefined) ?? null,
      loading: true,
      failure: null,
      cachedAt: null,
    });
    fetchRef
      .current()
      .then(value => {
        cache.set(key, { value, at: Date.now() });
        live &&
          setState({
            data: value,
            loading: false,
            failure: null,
            cachedAt: null,
          });
      })
      .catch(e => {
        const old = cache.get(key);
        live &&
          setState({
            data: (old?.value as T | undefined) ?? null,
            loading: false,
            failure: failureOf(e),
            cachedAt: old?.at ?? null,
          });
      })
      .finally(() => live && setRefreshing(false));
    return () => {
      live = false;
    };
  }, [key, tick]);

  const refresh = useCallback(() => {
    setRefreshing(true);
    setTick(t => t + 1);
  }, []);
  return { ...state, refreshing, refresh } as Read<T>;
}

export function pullToRefresh(
  r: Pick<Read<unknown>, 'refreshing' | 'refresh'>,
) {
  return <RefreshControl refreshing={r.refreshing} onRefresh={r.refresh} />;
}

export function clock(ms: number): string {
  return new Date(ms).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export const MESSAGES = {
  offline:
    "Can't reach the server. Check your connection, then pull down to retry.",
  error: 'Something went wrong loading this. Pull down to retry.',
} as const;

// The loading, failure and stale-copy states shared by every read screen. Renders nothing when
// there is data and no problem, so the caller shows its own content.
export function ReadState({
  read,
  notFoundText,
}: {
  read: Read<unknown>;
  notFoundText?: string;
}) {
  if (read.data !== null) {
    return read.failure && read.cachedAt !== null ? (
      <Text style={styles.stale} accessibilityLiveRegion="polite">
        {`Last updated ${clock(read.cachedAt)}. Can't reach the server.`}
      </Text>
    ) : null;
  }
  if (read.loading) {
    return (
      <View accessibilityLabel="Loading" style={styles.center}>
        <ActivityIndicator color={colors.chalk} />
      </View>
    );
  }
  const text =
    read.failure === 'offline'
      ? MESSAGES.offline
      : read.failure === 'notfound' && notFoundText
      ? notFoundText
      : MESSAGES.error;
  return (
    <Text style={styles.failure} accessibilityLiveRegion="polite">
      {text}
    </Text>
  );
}

const styles = StyleSheet.create({
  center: { paddingVertical: 24, alignItems: 'center' },
  stale: type.meta,
  failure: { ...type.body, color: colors.bad },
});
