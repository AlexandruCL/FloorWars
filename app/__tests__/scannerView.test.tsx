import { render, screen } from '@testing-library/react-native';
import { useCameraDevice } from 'react-native-vision-camera';
import { ScannerView } from '../src/checkin/deviceLibs';

const mockDevice = useCameraDevice as jest.Mock;

test('shows a placeholder, without throwing, while the camera device is loading', async () => {
  mockDevice.mockReturnValue(undefined);
  await render(<ScannerView onScan={jest.fn()} />);
  expect(screen.getByText('Starting camera...')).toBeTruthy();
  expect(screen.queryByTestId('camera')).toBeNull();
});

test('renders the camera once a device exists', async () => {
  mockDevice.mockReturnValue({ id: 'back' });
  await render(<ScannerView onScan={jest.fn()} />);
  expect(screen.queryByText('Starting camera...')).toBeNull();
  expect(screen.getByTestId('camera')).toBeTruthy();
});
