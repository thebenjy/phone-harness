# iPhone Mirroring won't connect (bug issue, runbook, log, spec)

Date: 2026-11-25
Status: OPEN, unresolved. Pairing is stuck, the cause is not confirmed.
Scope: one-off investigation. Not part of the phone-harness codebase.

## 1. Issue

phone-harness iOS control needs iPhone Mirroring. On this Mac the Mirroring
window opens as a blank grey phone outline and shows "unable to connect to
iPhone". "Try again" does nothing. It used to work. It fails for both iPhones
(Test iphone 12pro and a second iPhone), so the fault is Mac-side.

`phone_doctor` (ios) result:

- PASS: pyobjc frameworks, Accessibility, Screen Recording, iPhone Mirroring installed
- FAIL: iPhone Mirroring running (auto-launches, not fatal)
- FAIL: mirroring window found ("open iPhone Mirroring once manually to pair the phone")

`screen()` returns `[]` and `screenshot()` returns the empty grey outline.

## 2. Environment

- Mac: macOS 26.4 (build 25E246), Darwin 25.4.0, up 8 days at time of test.
  An old memory note says macOS 12.6.7. That is stale. iPhone Mirroring is supported.
- iPhone: Test iphone 12pro (iOS version not yet confirmed; needs iOS 18+).
- Network: Wi-Fi `en1` 192.168.8.15 and Ethernet `en0` 192.168.8.6, same subnet,
  gateway 192.168.8.1. Ethernet was the primary route.
- Tailscale was installed and connected.
- Region: Australia (en-AU, UTC+10).

## 3. Findings

Seen on the Mac:

- System Settings > General > AirPlay & Continuity > iPhone row shows
  "Test iphone 12pro: Pairing in progress. This iPhone will be used for iPhone
  Mirroring when pairing is complete." It never completes.
- The dropdown only offers "iPhone" and "Test iphone 12pro". There is no "None".
- `rapportd` logs show the phone over BLE: same iCloud account (`MyMe MyiCloud`),
  screen active, RSSI about -60 dBm (close). The Mac-to-phone link is visible.
- No iPhone appears on USB. Mirroring does not use the cable.
- The iPhone does not list the Mac under Settings > General > AirPlay & Continuity
  > iPhone Mirroring.
- The Mirroring app logs show no error. It launches, then either quits once
  or stays blank.

Ruled out (checked, no change):

- Mac OS version: supported.
- Config profiles / MDM: none (`profiles list`).
- Firewall: disabled. Block-all disabled.
- Bluetooth: On (BCM_4388C2). Wi-Fi: On, connected (`system_profiler SPAirPortDataType`).
- AWDL `awdl0`: status active.
- Tailscale: quit. VPN service showed Disconnected. No change.
- Ethernet: unplugged by the user, Wi-Fi only. No change.
- iPhone settings: phone locked, no Personal Hotspot, Handoff and Handoff to
  Home Devices on, Bluetooth toggled off/on, Handoff toggled off/on. No change.
- Daemon restart: `killall rapportd sharingd identityservicesd`, then relaunch
  Mirroring. No change.

Note: my first pointer (Desktop & Dock > Widgets > iPhone) was wrong. The iPhone
row lives in General > AirPlay & Continuity. Deep link:
`open "x-apple.systempreferences:com.apple.AirDrop-Handoff-Settings.extension"`.

## 4. Diagnosis

Cause is not confirmed. Working hypothesis, from the evidence: the Mac's
Continuity pairing or Apple ID registration is corrupt, or the Bluetooth/AWDL
stack needs a full restart. Both phones failing points to the Mac, not the
phones. A macOS 26.4 bug is possible and untested.

## 5. Runbook (in order)

1. Restart the Mac (full restart, not just the daemons). Keep the iPhones locked
   and nearby, Ethernet unplugged. Open iPhone Mirroring first after boot.
2. In AirPlay & Continuity, select the other iPhone entry, wait 10 s, then
   re-select Test iphone 12pro. Toggle iPhone Widgets on, then off.
3. Full power-off and power-on of the iPhone. Confirm iOS is 18 or later.
4. Sign out of iCloud on the Mac, restart, sign in again. Confirm the same Apple
   ID as the iPhones, with two-factor on. Sign-out may remove local iCloud data
   (Desktop & Documents sync, Keychain). Confirm the prompts before proceeding.
5. If it still fails, test a different Wi-Fi network or a phone hotspot to rule
   out router isolation, and check whether another Mac on the same Apple ID pairs.
6. After every step, run `phone_doctor` (platform ios). Success is the mirroring
   window check passing and `screen()` returning text boxes.

Fallback if the Mac cannot be fixed: a cloud iPhone (`phone-harness cloud login`,
`cloud ls`, `cloud start PHONE`). It needs no pairing but is not the physical
Test iphone 12pro.

## 6. Log

| Time (UTC+10) | Action | Result |
| --- | --- | --- |
| 13:33 | `phone_doctor` ios, launch Mirroring | Mirroring not running, no window; app quit at launch |
| 13:34 | Relaunch, `screen()` / `screenshot()` | Blank grey outline, `[]` |
| 13:38 | User quit Tailscale, relaunch | No change |
| 13:42 | Opened AirPlay & Continuity pane | "Pairing in progress" for Test iphone 12pro |
| 13:51 | Checked profiles, firewall, Bluetooth, Wi-Fi | All fine |
| 13:51 | Restarted rapportd, sharingd, identityservicesd | No change |
| after | User unplugged Ethernet | No change |

## 7. Spec for done

- iPhone Mirroring shows the phone's home screen on the Mac.
- `phone_doctor` ios passes all checks.
- `phone_exec` with `ensure_device()` then `screen()` returns text boxes with
  tap coordinates for Test iphone 12pro.
- Record the fix that worked in section 6 and update the memory note about
  macOS 12 / no iPhone Mirroring.

## 8. Open questions

- iOS version of the iPhone(s)?
- What is the second dropdown entry "iPhone"? A second device on the Apple ID?
- Did this break after a macOS or iOS update? When did it last work?
