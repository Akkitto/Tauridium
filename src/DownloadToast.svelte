<script lang="ts">
  import { onMount, tick } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { listen } from "@tauri-apps/api/event";
  import { ToastCountdown, type DownloadToastSnapshot } from "./lib/downloadToast";

  let snapshot = $state<DownloadToastSnapshot | null>(null);
  let hovered = $state(false);
  let focused = $state(false);
  let busy = $state(false);
  let failure = $state("");
  let positioned = $state(false);
  let card: HTMLElement;
  let countdown: ToastCountdown | null = null;
  let timerKey = "";
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  let systemDark = $state(media.matches);
  const dark = $derived(snapshot?.theme === "dark" || snapshot?.theme === "oled" || (snapshot?.theme === "system" && systemDark));

  async function dismiss(expectedId?: number) {
    const id = snapshot?.completion?.id;
    if (id === undefined || busy || (expectedId !== undefined && expectedId !== id)) return;
    busy = true;
    failure = "";
    try {
      await invoke("dismiss_download_toast", { id });
    } catch (error) {
      failure = `Unable to dismiss notification: ${error}`;
    } finally {
      busy = false;
    }
  }

  function measure() {
    const id = snapshot?.completion?.id;
    if (id === undefined || !card) return;
    const height = Math.max(80, Math.min(240, Math.ceil(card.getBoundingClientRect().height)));
    void invoke("resize_download_toast", { id, height, pixelRatio: window.devicePixelRatio }).then(() => { positioned = true; }).catch((error) => {
      failure = `Unable to position notification: ${error}`;
    });
  }

  $effect(() => {
    if (!snapshot?.completion) return;
    // Off-screen native webviews may not receive animation frames. Measure
    // after Svelte's DOM flush so the first toast can become visible promptly.
    let cancelled = false;
    void tick().then(() => { if (!cancelled) measure(); });
    return () => { cancelled = true; };
  });

  $effect(() => {
    const key = `${snapshot?.completion?.id ?? ""}:${snapshot?.duration ?? 0}`;
    if (key !== timerKey) {
      countdown?.dispose();
      timerKey = key;
      const id = snapshot?.completion?.id;
      countdown = id !== undefined && snapshot ? new ToastCountdown(snapshot.duration, () => { void dismiss(id); }) : null;
    }
    if (snapshot?.active && !hovered && !focused && !busy && !failure && positioned) countdown?.resume();
    else countdown?.pause();
  });

  onMount(() => {
    let disposed = false;
    let unlisten: (() => void) | null = null;
    let receivedEvent = false;
    const updateSystemTheme = () => { systemDark = media.matches; };
    media.addEventListener("change", updateSystemTheme);
    const observer = new ResizeObserver(measure);
    observer.observe(card);
    // Subscribe first so an old initial fetch cannot overwrite a newer event.
    void (async () => {
      try {
        const stop = await listen<DownloadToastSnapshot>("download-toast", (event) => {
          receivedEvent = true;
          snapshot = event.payload;
        });
        if (disposed) { stop(); return; }
        unlisten = stop;
        const initial = await invoke<DownloadToastSnapshot>("get_download_toast");
        if (!disposed && !receivedEvent) snapshot = initial;
      } catch (error) {
        if (!disposed) failure = `Unable to load download notification: ${error}`;
      }
    })();
    return () => {
      disposed = true;
      unlisten?.();
      observer.disconnect();
      media.removeEventListener("change", updateSystemTheme);
      countdown?.dispose();
    };
  });
</script>

<svelte:window onresize={measure} onkeydown={(event) => { if (event.key === "Escape") { event.preventDefault(); void dismiss(); } }} />

<section bind:this={card} class="download-toast-card" class:dark class:oled={snapshot?.theme === "oled"} class:unpositioned={!positioned}
  aria-label="Download notification"
  onpointerenter={() => { hovered = true; }} onpointerleave={() => { hovered = false; }}
  onfocusin={() => { focused = true; }} onfocusout={(event) => { focused = event.relatedTarget instanceof Node && card.contains(event.relatedTarget); }}>
  <div class="download-toast-content" role="status" aria-live="polite" aria-atomic="true" aria-busy={!positioned}>
    {#if snapshot?.completion}
      <div class="download-toast-heading"><span aria-hidden="true">↓</span><strong>{snapshot.completion.count > 1 ? `${snapshot.completion.count} downloads complete` : "Download complete"}</strong></div>
      {#if snapshot.completion.filename}<p class="download-toast-filename">{snapshot.completion.filename}</p>{/if}
      {#if snapshot.completion.location}<p class="download-toast-location"><span>{snapshot.completion.locationLabel}:</span> <bdi>{snapshot.completion.location}</bdi></p>{/if}
      {#if snapshot.waiting > 0}<p class="download-toast-waiting">{snapshot.waiting} more {snapshot.waiting === 1 ? "download" : "downloads"} waiting</p>{/if}
    {/if}
    {#if failure}<p class="download-toast-error">{failure}</p>{/if}
  </div>
  <button type="button" class="download-toast-dismiss" aria-label="Dismiss download notification" disabled={busy || !snapshot?.completion} onclick={() => { void dismiss(); }}>×</button>
</section>

<style>
  :global(body:has(.download-toast-card)) { margin: 0; padding: 0; background: transparent; overflow: hidden; }
  .download-toast-card { box-sizing: border-box; display: grid; grid-template-columns: minmax(0, 1fr) 30px; align-items: start; gap: 12px; min-height: 80px; width: 100%; max-height: 240px; padding: 12px 14px; border: 1px solid #aeb6c2; border-radius: 9px; background: #f5f7fa; color: #18202b; font: 13px/1.4 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  .download-toast-card.dark { background: #20242b; color: #f6f7f9; border-color: #566170; }
  .download-toast-card.unpositioned { visibility: hidden; }
  .download-toast-card.oled { background: #080808; }
  .download-toast-content { min-width: 0; max-height: 212px; overflow: auto; }
  .download-toast-heading { display: flex; gap: 8px; align-items: center; }
  .download-toast-heading > span { font-size: 19px; line-height: 1; color: #187a45; }
  .dark .download-toast-heading > span { color: #78dfa4; }
  p { margin: 5px 0 0; overflow-wrap: anywhere; }
  .download-toast-filename { max-height: 38px; overflow: auto; user-select: text; }
  .download-toast-location { max-height: 76px; overflow: auto; user-select: text; }
  .download-toast-location > span { font-weight: 600; }
  .download-toast-waiting { font-size: 12px; opacity: .8; }
  .download-toast-error { max-height: 48px; overflow: auto; color: #b82020; }
  .dark .download-toast-error { color: #ffb4b4; }
  .download-toast-dismiss { box-sizing: border-box; width: 30px; height: 30px; min-height: 0; padding: 0; border: 1px solid transparent; border-radius: 6px; background: transparent; color: inherit; font: 22px/1 system-ui, sans-serif; cursor: pointer; }
  .download-toast-dismiss:hover { background: #80808022; }
  .download-toast-dismiss:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }
  .download-toast-dismiss:disabled { opacity: .5; cursor: default; }
</style>
