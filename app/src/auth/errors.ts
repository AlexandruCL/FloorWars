import { ApiError } from '../api/client';

type Where = 'otp' | 'verify' | 'teams' | 'join';

// Every message says what to do next. A fetch that never got an answer is a TypeError.
export function describeError(e: unknown, where: Where): string {
  if (!(e instanceof ApiError)) {
    return "No connection. Try again when you're online.";
  }
  const { status } = e;
  if (status === 429) {
    return where === 'verify'
      ? 'Too many wrong codes. Go back and ask for a new code.'
      : 'Too many tries. Wait a few minutes, then try again.';
  }
  if (status >= 500) {
    return 'The service is busy. Try again in a minute.';
  }
  if (where === 'otp' && status === 403) {
    return "That address can't get a code. Use your university e-mail.";
  }
  if (where === 'verify' && status === 401) {
    return 'Check the code and try again. Codes expire after 10 minutes.';
  }
  if (where === 'verify' && status === 403) {
    return 'Confirm you are 18 or older and accept the terms, then try again.';
  }
  if (status === 401) {
    return 'Your session ended. Sign in again.';
  }
  if (status === 422) {
    return where === 'otp'
      ? 'Check the e-mail address and try again.'
      : 'Check the code and try again.';
  }
  if (status === 404 && where === 'teams') {
    return 'No season is running right now. Check back soon.';
  }
  return 'Something went wrong. Try again.';
}

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const OTP_RE = /^[0-9]{6}$/;
