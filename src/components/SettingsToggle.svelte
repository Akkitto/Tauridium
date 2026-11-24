<script lang="ts">

  import type { AppSettings } from "../lib/api";
  interface Props {
    label: string;
    description: string;
    settingKey: keyof AppSettings;
    checked: boolean;
    onsave: (key: keyof AppSettings, value: unknown) => Promise<void>;
  }
  let {
    label,
    description,
    settingKey,
    checked,
    onsave,
  }: Props = $props();
</script>

<label class="setting-card setting-card-toggle" id={`settings-option-${settingKey}`}>
    <span class="setting-copy"><span class="setting-label">{label}</span><span class="setting-description">{description}</span></span>
    <span class="switch-control">
      <input class="switch-input" type="checkbox" {checked} aria-label={label} onchange={(e) => onsave(settingKey, e.currentTarget.checked)} />
      <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
    </span>
  </label>
<style>

  input { font-family: inherit; }
  label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }
  input {
    padding: 9px 11px; border-radius: 8px; border: 1px solid var(--border2);
    background: var(--input); color: var(--text); font-size: 14px;
  }
  .setting-card:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
  }
  .setting-card {
    width: 100%; box-sizing: border-box; display: grid; grid-template-columns: minmax(0, 1fr) auto;
    align-items: center; gap: 18px; min-height: 68px; padding: 13px 14px;
    border: 1px solid var(--border); border-radius: 10px; background: var(--input);
    color: var(--text); text-align: left; font: inherit;
  }
  .setting-copy { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .setting-label { color: var(--text2); font-size: 14px; line-height: 1.35; font-weight: 650; }
  .setting-description { max-width: 760px; color: var(--muted); font-size: 12.5px; line-height: 1.45; font-weight: 400; }
  .switch-control { position: relative; width: 38px; height: 22px; flex: none; }
  .switch-input { position: absolute; inset: 0; width: 38px; height: 22px; margin: 0; opacity: 0; cursor: pointer; z-index: 1; }
  .switch-track { position: absolute; inset: 0; border: 1px solid var(--border2); border-radius: 999px; background: var(--bg); transition: background 0.15s ease, border-color 0.15s ease; }
  .switch-thumb { position: absolute; width: 16px; height: 16px; left: 2px; top: 2px; border-radius: 50%; background: var(--muted); transition: transform 0.15s ease, background 0.15s ease; }
  .switch-input:checked + .switch-track { background: var(--accent); border-color: var(--accent); }
  .switch-input:checked + .switch-track .switch-thumb { transform: translateX(16px); background: var(--accent-fg); }
  .switch-input:focus-visible + .switch-track { outline: 2px solid var(--accent); outline-offset: 2px; }
  .setting-card-toggle { cursor: pointer; }
  .setting-card-toggle:hover { background: var(--hover); border-color: var(--border2); }
  @media (max-width: 760px) {
    .setting-card { grid-template-columns: 1fr; gap: 10px; align-items: stretch; }
    .setting-card-toggle { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
  }

</style>
