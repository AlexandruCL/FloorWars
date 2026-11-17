import { useEffect, useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { hasSeenOnboarding } from '../auth/session';
import { EmailScreen, OtpScreen, TeamScreen } from '../screens/AuthScreens';
import { CheckinScreen } from '../screens/CheckinScreen';
import { LandingScanScreen } from '../screens/LandingScanScreen';
import { OnboardingScreen } from '../screens/OnboardingScreen';
import { HomeScreen } from '../screens/HomeScreen';
import { SensorLoggerScreen } from '../screens/SensorLoggerScreen';
import type {
  AuthStackParamList,
  MainStackParamList,
  RootStackParamList,
} from './types';

const RootStack = createNativeStackNavigator<RootStackParamList>();
const AuthStack = createNativeStackNavigator<AuthStackParamList>();
const MainStack = createNativeStackNavigator<MainStackParamList>();

type Props = {
  isSignedIn: boolean;
  // Tokens are stored but no team chosen yet: reopen on the team screen.
  needsTeam?: boolean;
  onSignedIn?: () => void;
  onDevSkipSignIn?: () => void;
};

function AuthNavigator({
  needsTeam,
  onSignedIn,
  onDevSkipSignIn,
}: Pick<Props, 'needsTeam' | 'onSignedIn' | 'onDevSkipSignIn'>) {
  return (
    <AuthStack.Navigator initialRouteName={needsTeam ? 'Team' : 'Email'}>
      <AuthStack.Screen name="Email" options={{ title: 'Sign in' }}>
        {props => <EmailScreen {...props} onDevSkipSignIn={onDevSkipSignIn} />}
      </AuthStack.Screen>
      <AuthStack.Screen name="Otp" options={{ title: 'Enter code' }}>
        {props => <OtpScreen {...props} />}
      </AuthStack.Screen>
      <AuthStack.Screen
        name="Team"
        options={{ title: 'Your team', headerBackVisible: false }}
      >
        {() => <TeamScreen onDone={() => onSignedIn?.()} />}
      </AuthStack.Screen>
    </AuthStack.Navigator>
  );
}

function MainNavigator() {
  // Shown once, right after the team choice; null until the stored flag is read.
  const [seen, setSeen] = useState<boolean | null>(null);
  useEffect(() => {
    hasSeenOnboarding().then(setSeen, () => setSeen(true));
  }, []);
  if (seen === null) {
    return null;
  }
  return (
    <MainStack.Navigator initialRouteName={seen ? 'Home' : 'Onboarding'}>
      <MainStack.Screen
        name="Onboarding"
        component={OnboardingScreen}
        options={{ title: 'How it works' }}
      />
      <MainStack.Screen
        name="LandingScan"
        component={LandingScanScreen}
        options={{ title: 'Scan at the stairs' }}
      />
      <MainStack.Screen name="Home" component={HomeScreen} />
      <MainStack.Screen
        name="Checkin"
        component={CheckinScreen}
        options={{ title: 'Check in' }}
      />
      <MainStack.Screen
        name="SensorLogger"
        component={SensorLoggerScreen}
        options={{ title: 'Sensor logger' }}
      />
    </MainStack.Navigator>
  );
}

export function RootNavigator({
  isSignedIn,
  needsTeam,
  onSignedIn,
  onDevSkipSignIn,
}: Props) {
  return (
    <NavigationContainer>
      <RootStack.Navigator screenOptions={{ headerShown: false }}>
        {isSignedIn ? (
          <RootStack.Screen name="Main" component={MainNavigator} />
        ) : (
          <RootStack.Screen name="Auth">
            {() => (
              <AuthNavigator
                needsTeam={needsTeam}
                onSignedIn={onSignedIn}
                onDevSkipSignIn={onDevSkipSignIn}
              />
            )}
          </RootStack.Screen>
        )}
      </RootStack.Navigator>
    </NavigationContainer>
  );
}
