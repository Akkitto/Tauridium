<script lang="ts">
  import { onMount, tick } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { listen } from "@tauri-apps/api/event";
  import { stepServiceZoomPercent } from "./lib/ui";
  import { menuFocusIndex, type ServiceMenuAction, type ServiceMenuSnapshot } from "./lib/serviceMenu";

  const opaque = window.__TAURIDIUM_SERVICE_MENU_OPAQUE__ === true;
  let snapshot = $state<ServiceMenuSnapshot>({ revision: 0, menu: null });
  let positioned = $state(false);
  let busy = $state(false);
  let focused = false;
  let surface = $state<HTMLDivElement>();
  let menu = $state<HTMLDivElement>();

  function update(value: ServiceMenuSnapshot) {
    if (value.revision < snapshot.revision) return;
    positioned = false;
    busy = false;
    snapshot = value;
    document.body.classList.toggle("light", value.menu?.theme === "light");
    document.body.classList.toggle("oled", value.menu?.theme === "oled");
  }

  async function dismiss(restoreFocus = false) {
    if (!snapshot.menu) return;
    await invoke("dismiss_service_menu", { id: snapshot.revision, restoreFocus });
  }

  async function choose(action: ServiceMenuAction) {
    if (!snapshot.menu || busy) return;
    busy = true;
    try { await invoke("choose_service_menu", { id: snapshot.revision, action }); }
    catch (error) { busy = false; console.error(`Unable to select service menu action: ${error}`); await dismiss(true); }
  }

  function focusFirst() { menu?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus(); }

  function keydown(event: KeyboardEvent) {
    if (event.key === "Escape" || event.key === "Tab") {
      event.preventDefault();
      void dismiss(true).catch(console.error);
      return;
    }
    if (!menu) return;
    const items = [...menu.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
    const index = menuFocusIndex(event.key, items.indexOf(document.activeElement as HTMLButtonElement), items.length);
    if (index !== null) { event.preventDefault(); items[index]?.focus(); }
  }

  $effect(() => {
    const id = snapshot.revision;
    if (!snapshot.menu) return;
    let cancelled = false;
    void tick().then(async () => {
      if (cancelled || !surface) return;
      const size = surface.getBoundingClientRect();
      const content = menu?.getBoundingClientRect();
      if (!content) return;
      positioned = true;
      await tick();
      if (!cancelled && snapshot.revision === id) await invoke("measure_service_menu", { id, measurement: { width: size.width, height: size.height, pixelRatio: window.devicePixelRatio, insetX: content.left - size.left, insetY: content.top - size.top } });
    }).catch((error) => console.error(`Unable to prepare service menu: ${error}`));
    return () => { cancelled = true; };
  });

  onMount(() => {
    let disposed = false;
    let stop: (() => void) | undefined;
    let receivedEvent = false;
    void (async () => {
      const unlisten = await listen<ServiceMenuSnapshot>("service-menu-state", (event) => { receivedEvent = true; update(event.payload); });
      if (disposed) { unlisten(); return; }
      stop = unlisten;
      const initial = await invoke<ServiceMenuSnapshot>("get_service_menu");
      if (!disposed && !receivedEvent) update(initial);
    })().catch((error) => console.error(`Unable to load service menu: ${error}`));
    return () => { disposed = true; stop?.(); };
  });
</script>

<svelte:window onfocus={() => { focused = true; focusFirst(); }} onblur={() => {
  if (focused) void dismiss().catch(console.error);
  focused = false;
}} onkeydown={keydown} oncontextmenu={(event) => event.preventDefault()} />

<div bind:this={surface} class="service-menu-surface" class:opaque class:unpositioned={!positioned}>
  {#if snapshot.menu}
    {@const service = snapshot.menu}
    <div bind:this={menu} class="service-context-menu" role="menu" tabindex="-1" aria-label={`${service.label} actions`}>
      <button role="menuitem" disabled={busy} onclick={() => void choose("settings")}>Settings</button>
      <button role="menuitem" disabled={busy || !service.enabled} onclick={() => void choose("reload")}>Reload</button>
      <div class="service-context-separator" aria-hidden="true"></div>
      <button role="menuitem" disabled={busy || service.zoomPercent >= 200} onclick={() => void choose("zoom-in")}>Zoom in ({stepServiceZoomPercent(service.zoomPercent, 1)}%)</button>
      <button role="menuitem" disabled={busy || service.zoomPercent <= 50} onclick={() => void choose("zoom-out")}>Zoom out ({stepServiceZoomPercent(service.zoomPercent, -1)}%)</button>
      <button role="menuitem" disabled={busy || service.zoomPercent === 100} onclick={() => void choose("zoom-reset")}>Reset zoom (100%)</button>
      <div class="service-context-separator" aria-hidden="true"></div>
      <button role="menuitem" disabled={busy} onclick={() => void choose("duplicate")}>Duplicate</button>
      <div class="service-context-separator" aria-hidden="true"></div>
      <button role="menuitem" disabled={busy} class:context-danger={service.enabled} onclick={() => void choose("toggle")}>{service.enabled ? "Disable" : "Enable"}</button>
    </div>
  {/if}
</div>

<style>
  :global(body:has(.service-menu-surface)) { background: transparent; overflow: hidden; }
  .service-menu-surface { width: max-content; padding: 16px; }
  :global(body:has(.service-menu-surface.opaque)) { background: var(--panel); }
  .service-menu-surface.opaque { padding: 0; }
  .opaque .service-context-menu { max-height: calc(100vh - 12px); border-radius: 0; box-shadow: none; }
  .unpositioned { visibility: hidden; }
  .service-context-menu { width: 226px; max-height: calc(100vh - 44px); overflow-y: auto; padding: 5px; border: 1px solid var(--border2); border-radius: 9px; background: var(--panel); box-shadow: 0 14px 42px rgba(0, 0, 0, 0.45); }
  .service-context-menu button { width: 100%; min-height: 34px; padding: 7px 9px; border: 0; border-radius: 6px; background: transparent; color: var(--text2); text-align: left; cursor: pointer; font: inherit; }
  .service-context-menu button:hover:not(:disabled), .service-context-menu button:focus-visible { background: var(--hover); }
  .service-context-menu button:disabled { color: var(--muted2); cursor: default; }
  .service-context-menu button.context-danger { color: #ff9b9b; }
  .service-context-separator { height: 1px; margin: 4px 3px; background: var(--border); }
</style>
