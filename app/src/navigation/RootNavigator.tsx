import { useEffect, useMemo, useState } from 'react';
import {
  DarkTheme,
  getStateFromPath,
  NavigationContainer,
} from '@react-navigation/native';
import type { LinkingOptions, Theme } from '@react-navigation/native';
import {
  type BottomTabNavigationOptions,
  createBottomTabNavigator,
} from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { hasSeenOnboarding } from '../auth/session';
import { EmailScreen, OtpScreen, TeamScreen } from '../screens/AuthScreens';
import { CheckinScreen } from '../screens/CheckinScreen';
import { HistoryScreen } from '../screens/HistoryScreen';
import { HomeScreen } from '../screens/HomeScreen';
import { LandingScanScreen } from '../screens/LandingScanScreen';
import { OnboardingScreen } from '../screens/OnboardingScreen';
import { SensorLoggerScreen } from '../screens/SensorLoggerScreen';
import { BuildingScreen } from '../screens/BuildingScreen';
import { BuildingsScreen } from '../screens/BuildingsScreen';
import { RanksScreen } from '../screens/RanksScreen';
import { YouScreen } from '../screens/YouScreen';
import { useMe } from '../data/myTeam';
import { FlipBanner } from '../realtime/FlipBanner';
import { AccentContext, colors, fonts } from '../ui/parts';
import { teamTone } from '../ui/tone';
import { Pictogram, type PictogramName } from '../ui/Pictogram';
import type {
  AuthStackParamList,
  MainStackParamList,
  RootStackParamList,
  TabParamList,
} from './types';

// The lost-building notification opens floorwars://building/{id} (W4-1): Building on top of the
// Buildings tab, so Back lands on the list.
export const linking: LinkingOptions<RootStackParamList> = {
  prefixes: ['floorwars://'],
  config: {
    screens: {
      Main: {
        initialRouteName: 'Tabs',
        screens: {
          Building: {
            path: 'building/:buildingId',
            parse: { buildingId: Number },
          },
        },
      },
    },
  },
  getStateFromPath(path, options) {
    const state = getStateFromPath(path, options);
    const building = state?.routes[0]?.state?.routes.find(
      r => r.name === 'Building',
    );
    if (!building) {
      return state;
    }
    return {
      routes: [
        {
          name: 'Main',
          state: {
            routes: [
              { name: 'Tabs', state: { routes: [{ name: 'Buildings' }] } },
              building,
            ],
          },
        },
      ],
    };
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
const Tab = createBottomTabNavigator<TabParamList>();

const tabIcons: Record<keyof TabParamList, PictogramName> = {
  Climb: 'climb',
  Buildings: 'buildings',
  Ranks: 'ranks',
  You: 'you',
};

const tabOptions = ({
  route,
}: {
  route: { name: keyof TabParamList };
}): BottomTabNavigationOptions => ({
  headerShown: false,
  tabBarActiveTintColor: colors.chalk,
  tabBarInactiveTintColor: colors.chalkFaint,
  tabBarStyle: {
    backgroundColor: colors.raised,
    borderTopColor: colors.hairline,
  },
  tabBarLabelStyle: { fontFamily: fonts.semibold, fontSize: 13 },
  tabBarIcon: ({ color }) => (
    <Pictogram name={tabIcons[route.name]} color={color} />
  ),
});

// Four places, always one tap away; tabs never animate (DESIGN.md sections 4 and 11).
function TabsNavigator() {
  return (
    <Tab.Navigator screenOptions={tabOptions}>
      <Tab.Screen name="Climb" component={HomeScreen} />
      <Tab.Screen name="Buildings" component={BuildingsScreen} />
      <Tab.Screen name="Ranks" component={RanksScreen} />
      <Tab.Screen name="You" component={YouScreen} />
    </Tab.Navigator>
  );
}

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
  const me = useMe();
  const team = me.data?.team;
  const accent = useMemo(
    () => (team ? teamTone(team.color_hex) : null),
    [team],
  );
  useEffect(() => {
    hasSeenOnboarding().then(setSeen, () => setSeen(true));
  }, []);
  if (seen === null) {
    return null;
  }
  return (
    // Your team's tone is the app's only accent once the team is known.
    <AccentContext.Provider value={accent}>
      <MainStack.Navigator
        initialRouteName={seen ? 'Tabs' : 'Onboarding'}
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
          options={{ title: 'Scan stair sticker' }}
        />
        <MainStack.Screen
          name="Tabs"
          component={TabsNavigator}
          options={{ headerShown: false }}
        />
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
        <MainStack.Screen
          name="Building"
          component={BuildingScreen}
          options={{ title: '' }}
        />
        <MainStack.Screen
          name="History"
          component={HistoryScreen}
          options={{ title: 'Climbs' }}
        />
      </MainStack.Navigator>
      <FlipBanner />
    </AccentContext.Provider>
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
