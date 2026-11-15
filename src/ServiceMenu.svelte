<script lang="ts">
  import { onMount, tick } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { listen } from "@tauri-apps/api/event";
  import { nextMenuIndex, serviceMenuEntries, type ServiceMenuAction, type ServiceMenuSnapshot } from "./lib/serviceMenu";

  // The renderer of the service context menu. Service webviews are native siblings of the
  // shell and always paint above its DOM, so the menu lives in its own native child webview.
  let snapshot = $state<ServiceMenuSnapshot | null>(null);
  let menu: HTMLElement | undefined = $state();
  // A blur only dismisses the menu once it has actually held focus. While the native layer moves
  // this view into place it can briefly lose focus it never really had, and dismissing then would
  // leave an empty surface covering the shell.
  let focused = false;
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  let systemDark = $state(media.matches);
  const light = $derived(snapshot?.theme === "light" || (snapshot?.theme === "system" && !systemDark));
  const oled = $derived(snapshot?.theme === "oled");
  const entries = $derived(snapshot ? serviceMenuEntries(snapshot) : []);

  function buttons(): HTMLButtonElement[] {
    return menu ? [...menu.querySelectorAll<HTMLButtonElement>("button[role='menuitem']")] : [];
  }

  async function dismiss(restoreFocus: boolean, reason: "escape" | "blur") {
    const current = snapshot;
    if (!current) return;
    try {
      // The native layer decides: a blur caused by releasing the opening click is ignored.
      const closed = await invoke<boolean>("dismiss_service_menu", { id: current.id, restoreFocus, reason });
      if (closed && snapshot?.id === current.id) snapshot = null;
    } catch (error) {
      console.error(`Unable to dismiss the service menu: ${error}`);
      if (snapshot?.id === current.id) snapshot = null;
    }
  }

  async function choose(action: ServiceMenuAction) {
    const current = snapshot;
    if (!current) return;
    snapshot = null;
    try {
      await invoke("service_menu_action", { id: current.id, action });
    } catch (error) {
      console.error(`Unable to run the service menu action: ${error}`);
    }
  }

  function focusFirst() {
    void tick().then(() => buttons().find((button) => !button.disabled)?.focus());
  }

  function show(next: ServiceMenuSnapshot | null) {
    snapshot = next;
    focused = next !== null && document.hasFocus();
    if (next) focusFirst();
  }

  function handleBlur() {
    if (!focused) return;
    focused = false;
    void dismiss(false, "blur");
  }

  function keydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      void dismiss(true, "escape");
      return;
    }
    const items = buttons();
    const key = event.key === "Tab" ? (event.shiftKey ? "ArrowUp" : "ArrowDown") : event.key;
    const next = nextMenuIndex(key, items.indexOf(document.activeElement as HTMLButtonElement), items.map((button) => !button.disabled));
    if (next === null) return;
    event.preventDefault();
    items[next]?.focus();
  }

  onMount(() => {
    let disposed = false;
    let unlisten: (() => void) | null = null;
    let receivedEvent = false;
    const updateSystemTheme = () => { systemDark = media.matches; };
    media.addEventListener("change", updateSystemTheme);
    // Subscribe first so an old initial fetch cannot overwrite a newer event.
    void (async () => {
      try {
        const stop = await listen<ServiceMenuSnapshot | null>("service-menu", (event) => {
          receivedEvent = true;
          show(event.payload);
        });
        if (disposed) { stop(); return; }
        unlisten = stop;
        const initial = await invoke<ServiceMenuSnapshot | null>("get_service_menu");
        if (!disposed && !receivedEvent) show(initial);
      } catch (error) {
        console.error(`Unable to load the service menu: ${error}`);
      }
    })();
    return () => {
      disposed = true;
      unlisten?.();
      media.removeEventListener("change", updateSystemTheme);
    };
  });
</script>

<!-- Losing focus (a click anywhere else, or switching windows) dismisses it like a native menu. -->
<svelte:window onfocus={() => { focused = snapshot !== null; }} onblur={handleBlur} oncontextmenu={(event) => event.preventDefault()} />

{#if snapshot}
  <div
    bind:this={menu}
    class="service-menu"
    class:light
    class:oled
    class:opaque={!snapshot.transparent}
    role="menu"
    tabindex="-1"
    aria-label={`${snapshot.label} actions`}
    style={`width:${snapshot.width}px;height:${snapshot.height}px`}
    onkeydown={keydown}
  >
    {#each entries as entry, index (index)}
      {#if entry.kind === "separator"}
        <div class="separator" aria-hidden="true"></div>
      {:else}
        <button type="button" role="menuitem" class:danger={entry.danger} disabled={entry.disabled} onclick={() => { void choose(entry.action); }}>{entry.label}</button>
      {/if}
    {/each}
  </div>
{/if}

<style>
  :global(body:has(.service-menu)), :global(html:has(.service-menu)) { margin: 0; padding: 0; background: transparent; overflow: hidden; }
  /* Palette and metrics mirror the shell's original service context menu. The renderer is a
     separate document, so it carries its own copy instead of depending on shell styles. */
  .service-menu {
    --panel: #232633; --border: #2f3445; --border2: #3a3f55;
    --text2: #d6d9e6; --muted2: #6b7193; --hover: #262a3a;
    box-sizing: border-box; display: block; padding: 5px;
    border: 1px solid var(--border2); border-radius: 9px;
    background: var(--panel); color: var(--text2);
    font: 16px system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color-scheme: dark; user-select: none; cursor: default;
  }
  .service-menu.light {
    --panel: #ffffff; --border: #d6dae6; --border2: #c8cddc;
    --text2: #2a2f40; --muted2: #818aa6; --hover: #e4e7f0;
    color-scheme: light;
  }
  .service-menu.oled {
    --panel: #050505; --border: #242424; --border2: #343434;
    --text2: #dedede; --muted2: #777777; --hover: #121212;
  }
  /* Opaque child webviews (macOS) cannot show rounded corners over the shell. */
  .service-menu.opaque { border-radius: 0; }
  /* Fixed heights keep the layout exactly as tall as the native rectangle reserved for it:
     2 x (5px padding + 1px border) + 7 x 34px items + 3 x 9px separators = 277px. */
  button { display: block; box-sizing: border-box; width: 100%; height: 34px; padding: 0 9px; border: 0; border-radius: 6px; background: transparent; color: var(--text2); text-align: left; cursor: pointer; font: inherit; line-height: 34px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  button:hover:not(:disabled), button:focus-visible { background: var(--hover); outline: none; }
  button:disabled { color: var(--muted2); cursor: default; }
  button.danger { color: #ff9b9b; }
  .light button.danger { color: #c62828; }
  .separator { height: 1px; margin: 4px 3px; background: var(--border); }
</style>
