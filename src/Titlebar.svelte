<script lang="ts">
  import { onMount } from "svelte";
  import { listen } from "@tauri-apps/api/event";
  import { focusWindowContent, getWindowChrome, openWindowMenu, type WindowChrome } from "./lib/api";
  import logo from "./assets/tauridium.svg";

  let model = $state<WindowChrome | null>(null);
  let selected = $state(0);
  let busy = $state(false);
  let error = $state("");
  let buttons: HTMLButtonElement[] = [];
  const names = ["Tauridium", "Edit", "View", "Navigate", "Services", "About"];
  let width = $state(window.innerWidth);
  const compact = $derived(width < 590);
  const labels = $derived(compact ? ["Menu"] : names);

  function update(value: WindowChrome) {
    model = value;
    document.body.classList.add("window-titlebar");
    document.body.classList.toggle("light", value.theme === "light");
    document.body.classList.toggle("oled", value.theme === "oled");
    document.title = value.title;
  }

  function focus(index: number) {
    selected = Math.max(0, Math.min(labels.length - 1, index));
    buttons[selected]?.focus();
  }

  async function openMenu(index: number) {
    if (busy) return;
    selected = index;
    error = "";
    busy = true;
    try {
      await openWindowMenu(compact ? names.length : index, buttons[index]?.getBoundingClientRect().left ?? 0);
    } catch (err) {
      error = `Unable to open the application menu: ${err}`;
    } finally {
      busy = false;
    }
  }

  function keyboard(event: KeyboardEvent) {
    const index = menuKeyIndex(event.key, selected, labels.length);
    if (index !== null) { event.preventDefault(); focus(index); }
    else if (event.key === "ArrowDown") { event.preventDefault(); void openMenu(selected); }
    else if (event.key === "Escape" || event.key === "Tab") {
      event.preventDefault();
      void focusWindowContent().catch((err) => { error = `Unable to return to the app: ${err}`; });
    }
  }

  // Exported separately for focused keyboard regression tests.
  import { menuKeyIndex } from "./lib/windowChrome";

  onMount(() => {
    let closed = false;
    const cleanups: (() => void)[] = [];
    async function connect() {
      for (const registration of [
        listen<WindowChrome>("window-chrome-changed", (event) => update(event.payload)),
        listen<number>("window-chrome-focus-menu", (event) => focus(event.payload)),
      ]) {
        const unlisten = await registration;
        if (closed) unlisten(); else cleanups.push(unlisten);
      }
      const initial = await getWindowChrome();
      if (!closed) update(initial);
    }
    void connect().catch((err) => { if (!closed) error = `Unable to initialize the title bar: ${err}`; });
    return () => { closed = true; cleanups.forEach((cleanup) => cleanup()); };
  });
</script>

<svelte:window onresize={() => width = window.innerWidth} />

<header data-tauri-drag-region aria-label="Tauridium title bar" class:inactive={model && !model.active}>
  <div class="menu-bar" role="menubar" tabindex="-1" aria-label="Application" onkeydown={keyboard}>
    {#each labels as name, index}
      <button
        bind:this={buttons[index]}
        role="menuitem"
        aria-haspopup="menu"
        aria-expanded={busy && selected === index}
        tabindex={selected === index ? 0 : -1}
        onfocus={() => selected = index}
        onclick={() => openMenu(index)}
      >
        {#if index === 0}<img src={logo} alt="" draggable="false" />{/if}
        <span>{name}</span>
      </button>
    {/each}
  </div>
  <span data-tauri-drag-region class="window-title" title={error || model?.title || "Tauridium"} role={error ? "alert" : undefined}>
    {error ? "Application menu unavailable" : model?.title || "Tauridium"}
  </span>
  <span data-tauri-drag-region class="drag-clearance" aria-hidden="true"></span>
</header>

<style>
  :global(body.window-titlebar) { margin: 0; overflow: hidden; user-select: none; background: var(--bg); }
  header { box-sizing: border-box; display: flex; align-items: center; gap: 8px; height: 100vh; width: 100vw; overflow: hidden; padding-inline: 8px; color: var(--text); background: var(--bg); -webkit-app-region: drag; }
  .menu-bar { display: flex; align-items: center; flex-shrink: 0; -webkit-app-region: no-drag; }
  button { display: flex; align-items: center; gap: 6px; box-sizing: border-box; min-height: 30px; padding: 4px 9px; border: 1px solid transparent; border-radius: 4px; background: transparent; color: inherit; font: inherit; font-size: 12px; cursor: default; -webkit-app-region: no-drag; }
  button:hover, button[aria-expanded="true"] { background: var(--hover); }
  button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  button img { width: 16px; height: 16px; }
  .window-title { min-width: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: center; font-size: 12px; -webkit-app-region: drag; }
  .inactive .window-title { color: var(--muted); }
  .inactive .menu-bar { opacity: 0.65; }
  .drag-clearance { flex: 0 0 48px; height: 100%; -webkit-app-region: drag; }
  @media (max-width: 590px) { button { padding-inline: 6px; } .window-title { text-align: left; } }
  @media (forced-colors: active) { header { color: CanvasText; background: Canvas; } button:hover { background: Highlight; color: HighlightText; } button:focus-visible { outline-color: Highlight; } .inactive .menu-bar { opacity: 1; color: GrayText; } .inactive .window-title { color: GrayText; } }
</style>
