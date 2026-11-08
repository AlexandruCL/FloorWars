## W3-6: Sign out

Stacked on the outbox PR. It conflicts with the sync PR in one place: that PR replaces `PlaceholderScreens.tsx` with `HomeScreen.tsx`. When the sync PR has merged, rebase this one, take the new `HomeScreen.tsx` and carry over `confirmSignOut` and the button. That resolution is already tested on a throwaway merge branch (121 Jest tests green).

- A Sign out button on Home with a confirmation that says how many segments are not uploaded yet and that they will be deleted (`getPendingCount()`).
- `endSession()` calls `clearPending()` and `clearActiveCheckin()` (which also stops the sensors) before clearing tokens. A native failure does not stop the sign-out. The forced sign-out after a failed refresh does the same.
- Why `clearPending`: the contract gives the app no user id to tag rows with, so a different user signing in would otherwise inherit them.

### Verify
- `cd app && npm run lint && npm run typecheck && npm test`: clean, 11 suites, 82 tests

### Emulator click-through
Cancel kept the user on Home. Confirm returned to the e-mail screen. With a pending row the dialog said "1 segment is not uploaded yet and will be deleted"; after confirming, the pending count was 0 and the foreground service had stopped.

### Not done
There is no server revoke call yet, so the old refresh token stays valid until it expires. Ionut has `POST /auth/logout` on branch `feat/w3-auth-logout` (contract 0.7.0-draft). Once it merges, `endSession()` should call it best-effort before clearing tokens.

Tested against the Prism mock and an emulator only, not the real server.
