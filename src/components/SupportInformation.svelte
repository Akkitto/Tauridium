<script lang="ts">
  import { onMount } from "svelte";
  import { createSupportInformationController } from "../lib/controllers/supportInformation.svelte";

  let { compact = false }: { compact?: boolean } = $props();
  const support = createSupportInformationController();
  onMount(() => { void support.refresh(); });
</script>

<section class="support-information" class:compact aria-busy={support.busy} aria-labelledby="settings-support-information" id="settings-option-supportInformation">
  {#if !compact}
    <div class="support-heading">
      <h3 id="settings-support-information">Support information</h3>
      <p>Copy app, system and WebView details plus selected interface flags to include in a bug report.</p>
    </div>
    <p class="privacy-note">Excludes account details, service names and URLs, file paths, logs and credentials.</p>
  {:else}
    <span class="sr-only" id="settings-support-information">Support information</span>
  {/if}
  <div class="support-actions">
    <button type="button" class="secondary" disabled={support.busy} onclick={support.copy}
      title="Copy app, system and WebView details. Excludes account details, service names and URLs, paths, logs and credentials.">
      {support.busy ? "Preparing support information…" : "Copy support information"}
    </button>
  </div>
  <p class="feedback" class:success={!!support.status} class:failure={!!support.error} role="status" aria-live="polite" aria-atomic="true">{support.error || support.status}</p>
  <details>
    <summary>Preview support information</summary>
    <p class="preview-note">This preview is a snapshot. Copying refreshes the report; you choose where to paste and share it.</p>
    {#if support.text}
      <textarea readonly rows={12} value={support.text} aria-label="Support information preview" spellcheck={false}></textarea>
    {:else}
      <p class="preview-note">{support.busy ? "Preparing support information…" : "No support information is available yet."}</p>
    {/if}
    <button type="button" class="refresh" disabled={support.busy} onclick={support.refresh}>Refresh support information</button>
  </details>
</section>

<style>
  button, textarea { font-family: inherit; }
  .support-information { min-width: 0; display: flex; flex-direction: column; gap: 10px; padding: 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--input); }
  .support-heading h3 { margin: 0; font-size: 14px; }
  .support-heading p, .privacy-note, .preview-note { margin: 5px 0 0; color: var(--muted); font-size: 12px; line-height: 1.5; }
  .support-actions { display: flex; flex-wrap: wrap; gap: 8px; }
  .secondary { box-sizing: border-box; min-height: 34px; padding: 8px 12px; border: 1px solid var(--border2); border-radius: 8px; background: var(--hover); color: var(--text); font-weight: 600; cursor: pointer; }
  .secondary:hover { border-color: var(--accent); }
  button:disabled { opacity: 0.55; cursor: default; }
  button:focus-visible, summary:focus-visible, textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
  .feedback { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }
  .feedback:empty { display: none; }
  .success { color: var(--text); }
  .failure { color: var(--text); font-weight: 600; }
  summary { min-height: 28px; line-height: 28px; cursor: pointer; color: var(--text2); font-size: 12px; font-weight: 600; }
  textarea { display: block; box-sizing: border-box; width: 100%; min-width: 0; max-height: 360px; margin: 10px 0; resize: vertical; padding: 10px; border: 1px solid var(--border2); border-radius: 8px; background: var(--card); color: var(--text); font-size: 12px; line-height: 1.5; white-space: pre; overflow: auto; }
  .refresh { min-height: 28px; padding: 4px 0; background: transparent; border: 0; color: var(--text2); font-size: 12px; text-decoration: underline; cursor: pointer; }
  .compact { padding: 10px 0 0; border: 0; border-top: 1px solid var(--border); border-radius: 0; background: transparent; }
  .compact .secondary { width: 100%; font-size: 12px; }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
</style>
