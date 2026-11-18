import { Platform } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { markOnboardingSeen } from '../auth/session';
import { FloorSensors } from '../native/floorSensors';
import type { MainStackParamList } from '../navigation/types';
import { Body, Button, Heading, Screen } from '../ui/parts';

const SAMSUNG =
  "Settings > Apps > FloorWars > Battery > Unrestricted. Then Settings > Battery > Background usage limits, and make sure FloorWars isn't under Sleeping apps or Deep sleeping apps.";
const XIAOMI =
  'Settings > Apps > Manage apps > FloorWars > Battery saver > No restrictions. On the same page, turn on Autostart.';
const OTHER =
  "Settings > Apps > FloorWars > Battery, and choose Unrestricted or Don't optimise. The names differ between phones.";

export function batterySteps(manufacturer: unknown): string {
  const m = String(manufacturer ?? '').toLowerCase();
  if (m === 'samsung') {
    return SAMSUNG;
  }
  return ['xiaomi', 'redmi', 'poco'].includes(m) ? XIAOMI : OTHER;
}

export function OnboardingScreen({
  navigation,
}: NativeStackScreenProps<MainStackParamList, 'Onboarding'>) {
  const done = async () => {
    await markOnboardingSeen().catch(() => {});
    // First run has no Home underneath; reopened from Home it does.
    if (navigation.canGoBack()) {
      navigation.goBack();
    } else {
      navigation.replace('Home');
    }
  };
  return (
    <Screen>
      <Heading>Before you climb</Heading>
      <Body>
        Walk, don't run. Points come from steps, never from speed: a slow climb
        scores the same as a fast one. Hold the handrail, and stop if you feel
        unwell. Taking the elevator is fine. It just doesn't score.
      </Body>
      <Heading>Physical activity</Heading>
      <Body>
        FloorWars counts your steps on stairs. Android calls this permission
        Physical activity. Without it, climbs aren't detected.
      </Body>
      <Heading>Notifications</Heading>
      <Body>
        Lets FloorWars show that it's detecting climbs while you're checked in,
        and tell you when another team takes your building.
      </Body>
      <Heading>Camera</Heading>
      <Body>
        Used only to scan the codes at building entrances and on stair landings.
        No photos are saved.
      </Body>
      <Heading>Location</Heading>
      <Body>
        Used once, when you check in by location, to find which building you're
        in. FloorWars doesn't track where you go.
      </Body>
      <Heading>Battery</Heading>
      <Body>
        Android can stop FloorWars in the background to save battery, and then
        climbs go missing. Let it run:
      </Body>
      <Body>{batterySteps((Platform.constants as any)?.Manufacturer)}</Body>
      <Button
        title="Open battery settings"
        secondary
        onPress={() => FloorSensors.openBatteryOptimizationSettings()}
      />
      <Button title="I've read this" onPress={done} />
    </Screen>
  );
}
