import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { HomeScreen, SignInScreen } from '../screens/PlaceholderScreens';
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
  onStubSignIn?: () => Promise<void>;
  onDevSkipSignIn?: () => void;
};

function AuthNavigator({
  onStubSignIn,
  onDevSkipSignIn,
}: Pick<Props, 'onStubSignIn' | 'onDevSkipSignIn'>) {
  return (
    <AuthStack.Navigator>
      <AuthStack.Screen name="SignIn" options={{ title: 'Sign in' }}>
        {() => (
          <SignInScreen
            onStubSignIn={onStubSignIn}
            onDevSkipSignIn={onDevSkipSignIn}
          />
        )}
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

// Session state arrives with the auth stub (T7); until then the caller decides.
export function RootNavigator({
  isSignedIn,
  onStubSignIn,
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
                onStubSignIn={onStubSignIn}
                onDevSkipSignIn={onDevSkipSignIn}
              />
            )}
          </RootStack.Screen>
        )}
      </RootStack.Navigator>
    </NavigationContainer>
  );
}
