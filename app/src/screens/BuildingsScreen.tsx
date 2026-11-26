import type { CompositeScreenProps } from '@react-navigation/native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { api } from '../api/client';
import { pullToRefresh, ReadState, useRead } from '../data/useRead';
import type { MainStackParamList, TabParamList } from '../navigation/types';
import { Body, Heading, Row, RowGroup, Screen } from '../ui/parts';

type Props = CompositeScreenProps<
  BottomTabScreenProps<TabParamList, 'Buildings'>,
  NativeStackScreenProps<MainStackParamList>
>;

// Every building; a row opens its standings. Owners and drawings join in the screens step.
export function BuildingsScreen({ navigation }: Props) {
  const buildings = useRead('buildings', () => api('get', '/buildings'));
  const list = [...(buildings.data ?? [])].sort((a, b) =>
    a.name.localeCompare(b.name),
  );
  return (
    <Screen refreshControl={pullToRefresh(buildings)}>
      <Heading>Buildings</Heading>
      <ReadState read={buildings} />
      {buildings.data && list.length === 0 && (
        <Body>No buildings are set up for this season yet.</Body>
      )}
      {list.length > 0 && (
        <RowGroup>
          {list.map(b => (
            <Row
              key={b.id}
              title={b.name}
              onPress={() =>
                navigation.navigate('Building', { buildingId: b.id })
              }
            />
          ))}
        </RowGroup>
      )}
    </Screen>
  );
}
