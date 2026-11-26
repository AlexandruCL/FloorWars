import { useEffect, useState } from 'react';
import { DarkTheme, NavigationContainer } from '@react-navigation/native';
import type { LinkingOptions, Theme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { hasSeenOnboarding } from '../auth/session';
import { EmailScreen, OtpScreen, TeamScreen } from '../screens/AuthScreens';
import { CheckinScreen } from '../screens/CheckinScreen';
import { HistoryScreen } from '../screens/HistoryScreen';
import { HomeScreen } from '../screens/HomeScreen';
import { LandingScanScreen } from '../screens/LandingScanScreen';
import { LeaderboardsScreen } from '../screens/LeaderboardsScreen';
import { OnboardingScreen } from '../screens/OnboardingScreen';
import { SensorLoggerScreen } from '../screens/SensorLoggerScreen';
import { StandingsScreen } from '../screens/StandingsScreen';
import { colors, fonts } from '../ui/parts';
import type {
  AuthStackParamList,
  MainStackParamList,
  RootStackParamList,
} from './types';

// The lost-building notification opens floorwars://building/{id} (W4-1). Back from Standings goes Home.
const linking: LinkingOptions<RootStackParamList> = {
  prefixes: ['floorwars://'],
  config: {
    screens: {
      Main: {
        initialRouteName: 'Home',
        screens: {
          Standings: {
            path: 'building/:buildingId',
            parse: { buildingId: Number },
          },
        },
      },
    },
  },
};

// Headers, cards and the back arrow in the night palette; fontWeight stays normal so Android
// does not fake a bolder cut of the custom fonts.
const theme: Theme = {
  dark: true,
  colors: {
    ...DarkTheme.colors,
    primary: colors.chalk,
    background: colors.night,
    card: colors.night,
    text: colors.chalk,
    border: colors.hairline,
  },
  fonts: {
    regular: { fontFamily: fonts.regular, fontWeight: 'normal' },
    medium: { fontFamily: fonts.medium, fontWeight: 'normal' },
    bold: { fontFamily: fonts.display, fontWeight: 'normal' },
    heavy: { fontFamily: fonts.display, fontWeight: 'normal' },
  },
};

// The native header ignores theme fonts, so the title face is set here.
const headerOptions = {
  headerTitleStyle: { fontFamily: fonts.display, fontSize: 24 },
};

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
    <AuthStack.Navigator
      initialRouteName={needsTeam ? 'Team' : 'Email'}
      screenOptions={headerOptions}
    >
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
    <MainStack.Navigator
      initialRouteName={seen ? 'Home' : 'Onboarding'}
      screenOptions={headerOptions}
    >
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
      <MainStack.Screen name="Standings" component={StandingsScreen} />
      <MainStack.Screen name="Leaderboards" component={LeaderboardsScreen} />
      <MainStack.Screen
        name="History"
        component={HistoryScreen}
        options={{ title: 'Climb history' }}
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
    // Off while the Auth stack shows, so a link then is dropped.
    <NavigationContainer
      theme={theme}
      linking={{ ...linking, enabled: isSignedIn }}
    >
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
