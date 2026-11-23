<script lang="ts">
  import { onDestroy, tick } from "svelte";
  import { searchSettings, settingsTabLabel, type SettingsSearchContext, type SettingsSearchEntry } from "./lib/settingsSearch";

  let { context, onchoose, onsearchfocus, oncancel, mac = false }: {
    context: SettingsSearchContext;
    onchoose: (entry: SettingsSearchEntry) => Promise<string | null>;
    onsearchfocus: () => void;
    oncancel: () => void;
    mac?: boolean;
  } = $props();
  let query = $state("");
  let expanded = $state(false);
  let index = $state(0);
  let status = $state("");
  let input: HTMLInputElement | undefined = $state();
  let container: HTMLDivElement | undefined = $state();
  let request = 0;
  let destroyed = false;
  const matches = $derived(searchSettings(query, context));
  const visible = $derived(expanded && query.trim().length > 0);
  const selected = $derived(Math.min(index, Math.max(0, matches.length - 1)));

  export function dismiss() { expanded = false; status = ""; request++; oncancel(); }
  export function focus() {
    expanded = Boolean(query.trim()); index = 0; status = "";
    input?.focus({ preventScroll: true });
    input?.select();
    input?.scrollIntoView({ block: "nearest", behavior: "auto" });
  }
  onDestroy(() => { destroyed = true; request++; oncancel(); });
  function changed(event: Event & { currentTarget: HTMLInputElement }) {
    oncancel();
    query = event.currentTarget.value;
    expanded = Boolean(query.trim()); index = 0; status = ""; request++;
  }
  async function choose(entry: SettingsSearchEntry) {
    const current = ++request;
    expanded = false; status = "";
    try {
      const message = await onchoose(entry);
      if (!destroyed && current === request && message) status = message;
    } catch (failure) {
      if (!destroyed && current === request) status = `Unable to open ${entry.label}: ${String(failure)}`;
    }
  }
  async function keydown(event: KeyboardEvent) {
    if (event.isComposing || event.key === "Process") return;
    if (event.key === "Escape") {
      event.preventDefault(); event.stopPropagation();
      if (expanded) dismiss(); else { query = ""; status = ""; request++; }
    } else if ((event.key === "ArrowDown" || event.key === "ArrowUp") && matches.length) {
      event.preventDefault();
      index = !expanded ? (event.key === "ArrowDown" ? 0 : matches.length - 1)
        : Math.max(0, Math.min(matches.length - 1, selected + (event.key === "ArrowDown" ? 1 : -1)));
      expanded = true;
      await tick();
      if (destroyed || !expanded) return;
      document.getElementById(`settings-search-result-${matches[index]?.id}`)?.scrollIntoView({ block: "nearest", behavior: "auto" });
    } else if (event.key === "Enter" && visible && matches[selected]) {
      event.preventDefault(); event.stopPropagation();
      await choose(matches[selected]);
    } else if (event.key === "Tab") dismiss();
  }
</script>

<div class="settings-search" bind:this={container} onfocusout={(event) => { if (!(event.relatedTarget instanceof Node) || !container?.contains(event.relatedTarget)) expanded = false; }}>
  <div class="search-field">
    <input bind:this={input} value={query} type="text" inputmode="search" role="combobox" aria-label="Search settings" placeholder="Search settings…"
      aria-keyshortcuts={mac ? "Meta+f" : "Control+f"} maxlength="200" autocomplete="off" spellcheck="false" aria-autocomplete="list" aria-expanded={visible}
      aria-controls={visible ? "settings-search-results" : undefined}
      aria-activedescendant={visible && matches[selected] ? `settings-search-result-${matches[selected].id}` : undefined}
      aria-describedby="settings-search-help" oninput={changed} onkeydown={keydown}
      onfocus={() => { onsearchfocus(); expanded = Boolean(query.trim()); }} />
    {#if query}<button class="clear-search" type="button" aria-label="Clear settings search" onclick={() => { query = ""; dismiss(); focus(); }}>×</button>
    {:else}<kbd aria-hidden="true">{mac ? "⌘F" : "Ctrl+F"}</kbd>{/if}
  </div>
  <span class="search-help" id="settings-search-help">Use arrow keys to browse results, Enter to open a setting, and Escape to dismiss results.</span>
  {#if visible}
    <div class="search-results">
      <div id="settings-search-results" role="listbox" aria-label="Matching settings" class="result-list">
        {#each matches as entry, position (entry.id)}
          <button id={`settings-search-result-${entry.id}`} type="button" role="option" tabindex="-1" aria-selected={selected === position}
            class="search-result" onpointermove={() => index = position} onmousedown={(event) => event.preventDefault()} onclick={() => choose(entry)}>
            <span class="result-copy"><span class="result-label">{entry.label}</span><span class="result-description">{entry.description}</span></span>
            <span class="result-tab">{settingsTabLabel(entry.tab)}</span>
          </button>
        {/each}
      </div>
      <p class="result-count" role="status">{#if matches.length}{matches.length} matching {matches.length === 1 ? "setting" : "settings"}{:else}No settings match “{query}”. Try another name or keyword.{/if}</p>
    </div>
  {/if}
  {#if status}<p class="navigation-status" role="status">{status}</p>{/if}
</div>

<style>
  .settings-search { padding: 0 24px 14px; min-width: 0; }
  .search-field { position: relative; display: flex; align-items: center; }
  .search-field input { width: 100%; box-sizing: border-box; min-height: 40px; padding: 9px 76px 9px 12px; border: 1px solid var(--border2); border-radius: 8px; background: var(--input); color: var(--text); font: inherit; font-size: 13px; }
  .search-field input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  kbd { position: absolute; right: 12px; color: var(--muted); font: inherit; font-size: 11px; pointer-events: none; }
  .clear-search { position: absolute; right: 5px; top: 4px; height: 32px; width: 32px; padding: 0; border: 0; border-radius: 6px; background: transparent; color: var(--muted); cursor: pointer; font-size: 22px; }
  .clear-search:hover { background: var(--hover); color: var(--text); }
  .clear-search:focus-visible { outline: 2px solid var(--accent); }
  .search-help { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  .search-results { margin-top: 8px; border: 1px solid var(--border2); border-radius: 8px; overflow: hidden; background: var(--input); }
  .result-list { max-height: min(280px, 40vh); overflow-y: auto; overscroll-behavior: contain; }
  .search-result { width: 100%; box-sizing: border-box; display: flex; align-items: center; gap: 12px; text-align: left; padding: 10px 12px; background: transparent; border: 0; border-bottom: 1px solid var(--border); color: var(--text); cursor: pointer; font: inherit; }
  .search-result[aria-selected="true"] { background: var(--hover); box-shadow: inset 3px 0 var(--accent); }
  .result-copy { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .result-label { font-size: 13px; font-weight: 650; overflow-wrap: anywhere; }
  .result-description, .result-tab { font-size: 12px; line-height: 1.4; color: var(--muted); }
  .result-tab { flex: none; max-width: 30%; overflow-wrap: anywhere; }
  .result-count, .navigation-status { margin: 0; padding: 8px 12px; font-size: 12px; line-height: 1.4; color: var(--muted); overflow-wrap: anywhere; }
  .navigation-status { padding: 8px 0 0; color: var(--text2); }
  @media (max-width: 760px) { .settings-search { padding-inline: 12px; } }
</style>
