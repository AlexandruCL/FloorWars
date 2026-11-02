import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { EmailScreen, OtpScreen, TeamScreen } from '../screens/AuthScreens';
import { HomeScreen } from '../screens/PlaceholderScreens';
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
  return (
    <MainStack.Navigator>
      <MainStack.Screen name="Home" component={HomeScreen} />
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
