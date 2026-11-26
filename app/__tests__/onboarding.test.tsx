import { fireEvent, render, screen } from '@testing-library/react-native';
import { Platform } from 'react-native';
import * as Keychain from 'react-native-keychain';
import { endSession, hasSeenOnboarding } from '../src/auth/session';
import { FloorSensors } from '../src/native/floorSensors';
import { RootNavigator } from '../src/navigation/RootNavigator';
import {
  batterySteps,
  OnboardingScreen,
} from '../src/screens/OnboardingScreen';

const sensors = FloorSensors as unknown as Record<string, jest.Mock>;
const READ = "I've read this";

beforeEach(async () => {
  await Keychain.resetGenericPassword({ service: 'floorwars.onboarding' });
  sensors.getStatus.mockResolvedValue({ has_barometer: true, detecting: true });
  sensors.getPendingCount.mockResolvedValue(0);
});

describe('flow', () => {
  test('shown first, then Home, and the flag is stored', async () => {
    await render(<RootNavigator isSignedIn />);
    await screen.findByText(READ, {}, { timeout: 5000 });
    await fireEvent.press(screen.getByText(READ));
    await screen.findByText('Sync now');
    expect(await hasSeenOnboarding()).toBe(true);
  });

  test('not cleared by sign-out', async () => {
    await Keychain.setGenericPassword('seen', '1', {
      service: 'floorwars.onboarding',
    });
    await endSession();
    expect(await hasSeenOnboarding()).toBe(true);
  });

  test('not shown again once seen; reopened from You, and closing it returns to You', async () => {
    await Keychain.setGenericPassword('seen', '1', {
      service: 'floorwars.onboarding',
    });
    await render(<RootNavigator isSignedIn />);
    await screen.findByText('Sync now', {}, { timeout: 5000 });
    expect(screen.queryByText(READ)).toBeNull();
    await fireEvent.press(await screen.findByText('You'));
    await fireEvent.press(await screen.findByText('How FloorWars works'));
    await fireEvent.press(await screen.findByText(READ));
    await screen.findByText('For testers');
  });
});

describe('manufacturer', () => {
  test.each([
    ['samsung', 'Settings > Apps > FloorWars > Battery > Unrestricted.'],
    ['Samsung', 'Settings > Apps > FloorWars > Battery > Unrestricted.'],
    ['Xiaomi', 'Settings > Apps > Manage apps'],
    ['REDMI', 'Settings > Apps > Manage apps'],
    ['poco', 'Settings > Apps > Manage apps'],
    [
      'google',
      "Settings > Apps > FloorWars > Battery, and choose Unrestricted or Don't optimise.",
    ],
    [
      undefined,
      "Settings > Apps > FloorWars > Battery, and choose Unrestricted or Don't optimise.",
    ],
  ])('%s', (m, start) => {
    expect(batterySteps(m).startsWith(start)).toBe(true);
  });

  test('the screen shows the section for Platform.constants.Manufacturer and asks no permission', async () => {
    const original = Platform.constants;
    Object.defineProperty(Platform, 'constants', {
      value: { ...original, Manufacturer: 'samsung' },
      configurable: true,
    });
    const navigation = { canGoBack: () => true, goBack: jest.fn() };
    await render(<OnboardingScreen {...({ navigation } as any)} />);
    screen.getByText(/Background usage limits/);
    expect(screen.queryByText(/Manage apps/)).toBeNull();
    await fireEvent.press(screen.getByText('Open battery settings'));
    expect(sensors.openBatteryOptimizationSettings).toHaveBeenCalled();
    Object.defineProperty(Platform, 'constants', {
      value: original,
      configurable: true,
    });
  });
});
