<script lang="ts">  import type { AppSettings, MeUser, Service, Workspace } from "../lib/api";
  import type { Snippet } from "svelte";

  interface Props {
    activeWorkspaceName: string;
    appSettings: AppSettings;
    appVer: string;
    me: MeUser;
    onServiceAreaDragOver: (e: DragEvent) => void;
    onServiceAreaDrop: (e: DragEvent) => Promise<void>;
    services: Service[];
    toggleSidebarCollapsed: () => void;
    visibleServices: Service[];
    workspaces: Workspace[];
    row: Snippet<[Service]>;
  }

  let {
    activeWorkspaceName,
    appSettings,
    appVer,
    me,
    onServiceAreaDragOver,
    onServiceAreaDrop,
    services,
    toggleSidebarCollapsed,
    visibleServices,
    workspaces,
    row,
  }: Props = $props();

</script>

<aside class="sidebar" class:collapsed={appSettings.sidebarCollapsed}>
      <div class="account">
        <div class="account-copy">
          <strong title={me.local ? "Local" : me.firstname || me.email}>{me.local ? "Local" : me.firstname || me.email}</strong>
          <span class="workspace-scope" title={activeWorkspaceName} aria-label={`Workspace: ${activeWorkspaceName}`}>{activeWorkspaceName}</span>
        </div>
        <button
          class="sidebar-collapse-button"
          type="button"
          aria-label={appSettings.sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-pressed={appSettings.sidebarCollapsed}
          title={`${appSettings.sidebarCollapsed ? "Expand" : "Collapse"} sidebar (${appSettings.keybindings.toggleSidebar || "unassigned"})`}
          onclick={toggleSidebarCollapsed}
        >
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <rect x="2.5" y="3.5" width="15" height="13" rx="2"></rect>
            <path d="M7 4v12"></path>
            {#if appSettings.sidebarCollapsed}
              <path d="m10.5 7 3 3-3 3"></path>
            {:else}
              <path d="m13.5 7-3 3 3 3"></path>
            {/if}
          </svg>
        </button>
      </div>

      <div class="svcarea" role="region" aria-label="Service list drop area" ondragover={onServiceAreaDragOver} ondrop={onServiceAreaDrop}>
        <div class="svclist">
          {#each visibleServices as s (s.id)}{@render row(s)}{/each}
        </div>
      </div>

      <div class="count">
        {services.length} services · {workspaces.length} workspaces{#if appVer} · <span class="ver">v{appVer}</span>{/if}
      </div>
    </aside>

<style>

  button { font-family: inherit; }
  .sidebar {
    background: var(--sidebar); padding: 10px 10px 8px; overflow: hidden;
    display: flex; flex-direction: column; gap: 8px;
  }
  .svcarea {
    flex: 1; min-height: 0; display: flex; flex-direction: column; overflow-y: auto;
    overscroll-behavior: contain; scrollbar-gutter: stable;
  }
  :global(body[data-svcloc="center"]) .svclist { margin-block: auto; }
  :global(body[data-svcloc="bottom"]) .svclist { margin-top: auto; }
  .account { display: flex; align-items: center; min-width: 0; min-height: 32px; font-size: 13px; }
  .account-copy { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
  .account strong { flex: 0 1 auto; min-width: 0; max-width: 45%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .workspace-scope { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted2); }
  .sidebar-collapse-button {
    width: 30px; height: 30px; margin-left: 6px; flex: none; display: grid; place-items: center;
    padding: 0; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--muted); cursor: pointer;
  }
  .sidebar-collapse-button:hover { border-color: var(--border); background: var(--hover); color: var(--text2); }
  .sidebar-collapse-button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .sidebar-collapse-button svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
  .sidebar.collapsed { padding-inline: 5px; }
  .sidebar.collapsed .account { width: 42px; justify-content: center; }
  .sidebar.collapsed .account-copy, .sidebar.collapsed .count { display: none; }
  .sidebar.collapsed .sidebar-collapse-button { margin-left: 0; }
  .sidebar.collapsed .svcarea { width: 42px; scrollbar-gutter: auto; scrollbar-width: none; }
  .sidebar.collapsed .svcarea::-webkit-scrollbar { width: 0; height: 0; }
  .sidebar.collapsed .svclist { gap: var(--collapsed-service-gap, 2px); }
  .sidebar.collapsed .svclist { width: 42px; }
  .svclist { display: flex; flex: none; flex-direction: column; gap: var(--expanded-service-gap, 2px); padding-right: 0; }
  .count { font-size: 11px; color: var(--muted2); }
  .ver { font-weight: 700; color: var(--muted); }

</style>
