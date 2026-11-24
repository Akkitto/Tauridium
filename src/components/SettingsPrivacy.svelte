<script lang="ts">

  import type { AppSettings } from "../lib/api";
  import SettingsToggle from "./SettingsToggle.svelte";

  interface Props {
    appSettings: AppSettings;
    saveAppSetting: (key: keyof AppSettings, value: unknown) => Promise<void>;
  }

  let {
    appSettings,
    saveAppSetting,
  }: Props = $props();

</script>

<section class="settings-section" aria-labelledby="settings-privacy-notifications">
                <div class="section-heading"><h3 id="settings-privacy-notifications">Notifications</h3><p>Limit message information exposed through operating-system notifications.</p></div>
                <div class="settings-list">
                <SettingsToggle
                  label={"Private notifications"}
                  description={"Hide sender and message content and show only a generic new-message notification."}
                  settingKey={"privateNotifications"}
                  checked={appSettings.privateNotifications}
                  onsave={saveAppSetting}
                />
                </div>
              </section>

<style>

  .settings-section { display: flex; flex-direction: column; gap: 10px; }
  .section-heading { display: flex; flex-direction: column; gap: 4px; padding: 0 2px; }
  .section-heading h3 { margin: 0; font-size: 13px; line-height: 1.3; font-weight: 700; color: var(--text); }
  .section-heading p { margin: 0; max-width: 840px; color: var(--muted); font-size: 12.5px; line-height: 1.45; }
  .settings-list { display: flex; flex-direction: column; gap: 8px; }

</style>
