<script lang="ts">  import type { QuickSwitcherMode } from "../lib/navigation";

  interface Props {
    activeId: string | null;
    activeWorkspace: string | null;
    chooseQuickSwitcherItem: (item: { id: string; kind: QuickSwitcherMode; }) => void;
    closeQuickSwitcher: (restore?: boolean) => void;
    quickSwitcherIndex: number;
    quickSwitcherItems: { id: string; label: string; kind: "workspace"; }[] | { id: string; label: string; kind: "service"; }[];
    quickSwitcherMode: QuickSwitcherMode | null;
    quickSwitcherQuery: string;
  }

  let {
    activeId,
    activeWorkspace,
    chooseQuickSwitcherItem,
    closeQuickSwitcher,
    quickSwitcherIndex = $bindable(),
    quickSwitcherItems,
    quickSwitcherMode,
    quickSwitcherQuery = $bindable(),
  }: Props = $props();

</script>

{#if quickSwitcherMode}
  <div class="quick-switcher-backdrop" role="presentation" onclick={(event) => event.currentTarget === event.target && closeQuickSwitcher()}>
    <div class="quick-switcher" role="dialog" aria-modal="true" aria-label={quickSwitcherMode === "service" ? "Quick service search" : "Quick workspace switcher"}>
      <div class="quick-switcher-head">
        <input
          type="search"
          value={quickSwitcherQuery}
          placeholder={quickSwitcherMode === "service" ? "Search services…" : "Search workspaces…"}
          aria-label={quickSwitcherMode === "service" ? "Search services" : "Search workspaces"}
          oninput={(event) => { quickSwitcherQuery = event.currentTarget.value; quickSwitcherIndex = 0; }}
        />
        <button class="icon-button" aria-label="Close quick switcher" title="Close" onclick={() => closeQuickSwitcher()}>×</button>
      </div>
      <div class="quick-switcher-results" role="listbox" aria-label="Quick switcher results">
        {#each quickSwitcherItems.slice(0, 100) as item, index (item.id)}
          <button
            class="quick-switcher-item"
            class:active={index === quickSwitcherIndex}
            class:current={(quickSwitcherMode === "workspace" && item.id === (activeWorkspace ?? "__all__")) || (quickSwitcherMode === "service" && item.id === activeId)}
            role="option"
            aria-selected={index === quickSwitcherIndex}
            aria-current={(quickSwitcherMode === "workspace" && item.id === (activeWorkspace ?? "__all__")) || (quickSwitcherMode === "service" && item.id === activeId) ? "true" : undefined}
            onmouseenter={() => (quickSwitcherIndex = index)}
            onclick={() => chooseQuickSwitcherItem(item)}
          >
            <span>{item.label}</span><small>{item.kind === "service" ? "Service" : "Workspace"}</small>
          </button>
        {:else}
          <div class="quick-switcher-empty">No matches</div>
        {/each}
      </div>
      {#if quickSwitcherItems.length > 100}<p class="quick-switcher-hint">Showing the first 100 matches. Refine your search to narrow the list.</p>{/if}
    </div>
  </div>
{/if}

<style>

  button, input { font-family: inherit; }
  input {
    padding: 9px 11px; border-radius: 8px; border: 1px solid var(--border2);
    background: var(--input); color: var(--text); font-size: 14px;
  }
  .icon-button {
    width: 34px; height: 34px; display: inline-grid; place-items: center; flex: none;
    border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--muted);
    cursor: pointer; font-size: 15px; line-height: 1;
  }
  .icon-button:hover { background: var(--hover); color: var(--text); border-color: var(--border); }
  .icon-button:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
  }
  .quick-switcher-backdrop { position: fixed; inset: 0; z-index: 1000; display: flex; justify-content: center; align-items: flex-start; padding-top: min(14vh, 120px); background: rgba(0, 0, 0, 0.46); }
  .quick-switcher { width: min(620px, calc(100vw - 32px)); max-height: min(68vh, 680px); overflow: hidden; display: flex; flex-direction: column; border: 1px solid var(--border2); border-radius: 12px; background: var(--panel); box-shadow: 0 18px 60px rgba(0, 0, 0, 0.48); }
  .quick-switcher-head { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; padding: 10px; border-bottom: 1px solid var(--border); }
  .quick-switcher-head input { width: 100%; box-sizing: border-box; min-height: 38px; }
  .quick-switcher-results { min-height: 48px; overflow-y: auto; overscroll-behavior: contain; padding: 6px; }
  .quick-switcher-item { width: 100%; min-height: 40px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 10px; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--text2); cursor: pointer; text-align: left; font: inherit; }
  .quick-switcher-item:hover, .quick-switcher-item.active { background: var(--hover); border-color: var(--border); }
  .quick-switcher-item small { color: var(--muted); font-size: 11px; }
  .quick-switcher-item.current { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
  .quick-switcher-item.current small { color: var(--accent-fg); opacity: 0.78; }
  .quick-switcher-empty, .quick-switcher-hint { padding: 16px; color: var(--muted); font-size: 12px; text-align: center; }
  .quick-switcher-hint { margin: 0; padding: 8px 12px; border-top: 1px solid var(--border); }

</style>
