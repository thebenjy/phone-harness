# Phone app under test

Read by Claude before driving the phone in this repo (phone-harness MCP: `phone_exec`,
`phone_doctor`). Keep it short and current. Never put passwords, PINs, tokens or 2FA codes here:
name the env var or the password-manager entry instead.

## App

- Name on the home screen: __APP_NAME__
- iOS bundle id: __IOS_BUNDLE_ID__
- Android package: __ANDROID_PACKAGE__
- Default platform for this repo: __PLATFORM__ (pass `platform="__PLATFORM__"` to `phone_exec`
  when the machine default differs)

## Build and install

Build and install from the shell before you drive the phone; phone-harness only launches what
is already installed.

- Android (device or cloud Android over adb):
  - Build + install: `TODO e.g. ./gradlew installDebug`, or `adb install -r path/to/app.apk`
  - Launch: `open_app("__ANDROID_PACKAGE__")`
- iOS: iPhone Mirroring cannot install a build. Install with `TODO e.g. Xcode / TestFlight / eas`,
  then `open_app("__APP_NAME__")`.

## Test accounts

- TODO: which account to use and where its credentials live (env var name, 1Password item).
  The agent never types passwords, PINs or 2FA codes; the user does that step.

## Flows worth checking

- TODO: e.g. "Onboarding: launch fresh, skip intro, land on Home with the tab bar visible."

## Do not

- Make purchases, send messages, or post anything from a real account without asking.
- Change phone settings without asking.
