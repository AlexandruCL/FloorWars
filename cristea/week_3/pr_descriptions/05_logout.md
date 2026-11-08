## Sign out revokes the refresh token on the server

Stacked on the sign-out PR (`feat/w3-signout`): until that PR merges, the diff also shows its commits and a merge of `main`. It uses Ionut's `POST /v1/auth/logout` (contract 0.7.0-draft, merged to `main` in #61).

- `app/src/auth/logout.ts`: `revokeRefreshToken()` sends the stored refresh token to `/auth/logout` through the generated client. It is best effort: no token, a network error, any 4xx or 5xx, and a server that does not answer within 5 s all end quietly.
- The Sign out handler (the confirm button) calls `revokeRefreshToken()` and then `endSession()`. It is **not** called inside `endSession()`, as agreed with Ionut, so the forced sign-out after a failed refresh does not call it (that token family is already revoked).
- `app/src/api/schema.ts` already contains `/auth/logout`: `npm run generate:api` leaves it unchanged after merging `main`.

### Verify
- `cd app && npm run lint && npm run typecheck && npm test`: clean, 12 suites, 88 tests
- `npm run generate:api`: `schema.ts` unchanged
- `cd app/android && ./gradlew test ktlintCheck`: BUILD SUCCESSFUL
- Removing the `await revokeRefreshToken()` line makes the handler test fail (checked once, then restored).

### Not verified
Not run on the emulator or against the real server. The tests cover the call, the order (logout before the Keychain is cleared), a failing call and a timeout.

When the sync PR merges, `confirmSignOut` moves into `HomeScreen.tsx` (see the sign-out PR). This PR then conflicts in one place: keep the `async onPress` that awaits `revokeRefreshToken()` and then `endSession()`.
