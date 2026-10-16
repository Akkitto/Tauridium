# Windows browser-profile privacy

Remote service webviews keep WebView2 tracking prevention and SmartScreen reputation
protection enabled by default. The app shell alone retains upstream custom-protocol
compatibility flags. This is not a website sandbox or a promise to block all trackers.

If an embedded sign-in/challenge genuinely fails, Windows service settings offer
**Reduce tracking prevention for sign-in compatibility**. It is off by default,
requires explicit confirmation and does not disable SmartScreen. Use the exception
only when needed; ordinary account/cookie isolation remains unchanged.

WebView2 environment options belong to the persistent browser profile. Therefore:

- An isolated service's exception affects only that service profile.
- For a shared sandbox, it affects **every service assigned to that sandbox**, including
  authentication popups. The UI states this before consent.
- Settings are saved/verified immediately, but **restart Tauridium to apply any change**.
  Reloading or hibernating a service is insufficient. All views sharing a profile use
  the same startup snapshot, avoiding incompatible environment options for an existing
  WebView2 user-data directory.
- New isolated clones do not inherit another service's exception. Deleted profile
  exceptions are removed during settings reconciliation. Settings backup/restore retains
  the explicit preference; restart after restoring browser privacy settings.

Windows runtime sign-in and reputation behavior must be verified on native Windows;
Linux compilation/UI tests cannot establish Microsoft Edge/WebView2 runtime behavior.
Linux and macOS do not apply this Windows-specific option.
