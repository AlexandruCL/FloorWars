import { useState } from 'react';
import { Platform, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { markOnboardingSeen } from '../auth/session';
import { FloorSensors } from '../native/floorSensors';
import type { MainStackParamList } from '../navigation/types';
import { Body, Button, colors, Heading, Screen, type } from '../ui/parts';

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
    // First run has no tabs underneath; reopened from You it does.
    if (navigation.canGoBack()) {
      navigation.goBack();
    } else {
      navigation.replace('Tabs');
    }
  };
  const [step, setStep] = useState(0);
  const next = () => setStep(n => n + 1);
  return (
    <Screen>
      <Text style={styles.count}>{`${step + 1} of 3`}</Text>
      {step === 0 && (
        <>
          <Heading>Walk, don't run</Heading>
          <Body>
            Walk, don't run. Points come from steps, never from speed: a slow
            climb scores the same as a fast one. Hold the handrail, and stop if
            you feel unwell. Taking the elevator is fine. It just doesn't score.
          </Body>
          <Button title="Next" onPress={next} />
        </>
      )}
      {step === 1 && (
        <>
          <Heading>What FloorWars uses</Heading>
          <View style={styles.uses}>
            <Text style={type.label}>Physical activity</Text>
            <Body>
              Counts your steps on stairs. Without it, climbs aren't detected.
            </Body>
            <Text style={type.label}>Notifications</Text>
            <Body>
              Shows detection is on, and tells you when another team takes your
              building.
            </Body>
            <Text style={type.label}>Camera</Text>
            <Body>
              Scans the codes at entrances and on stair landings. No photos are
              saved.
            </Body>
            <Text style={type.label}>Location</Text>
            <Body>
              Used once when you check in by location. FloorWars doesn't track
              where you go.
            </Body>
          </View>
          <Button title="Next" onPress={next} />
        </>
      )}
      {step === 2 && (
        <>
          <Heading>Keep it running</Heading>
          <Body>
            Android can stop FloorWars in the background to save battery, and
            then climbs go missing. Let it run:
          </Body>
          <Body>{batterySteps((Platform.constants as any)?.Manufacturer)}</Body>
          <Button
            title="Open battery settings"
            variant="text"
            onPress={() => FloorSensors.openBatteryOptimizationSettings()}
          />
          <Button title="Start climbing" onPress={done} />
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  count: { ...type.meta, color: colors.chalkDim },
  uses: { gap: 2 },
});
