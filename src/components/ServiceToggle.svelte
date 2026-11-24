<script lang="ts">

  import type { Service } from "../lib/api";
  interface Props {
    label: string;
    description: string;
    settingKey: keyof Service;
    checked: boolean;
    onsave: (key: keyof Service, value: boolean) => void;
  }
  let {
    label,
    description,
    settingKey,
    checked,
    onsave,
  }: Props = $props();
</script>

<div class="setrow">
    <label class="row-toggle">
      <input
        type="checkbox"
        {checked}
        onchange={(e) => onsave(settingKey, e.currentTarget.checked)}
      />
      <span>{label}</span>
    </label>
    <p class="desc">{description}</p>
  </div>
<style>

  input { font-family: inherit; }
  label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }
  input {
    padding: 9px 11px; border-radius: 8px; border: 1px solid var(--border2);
    background: var(--input); color: var(--text); font-size: 14px;
  }
  .row-toggle { flex-direction: row; align-items: center; gap: 10px; color: var(--text2); font-size: 14px; cursor: pointer; }
  .row-toggle input { width: auto; }
  .setrow { display: flex; flex-direction: column; gap: 3px; }
  .desc { margin: 0 0 0 26px; color: var(--muted); font-size: 12px; line-height: 1.35; }

</style>
