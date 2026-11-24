<script lang="ts">  import type { AppSettings, Service } from "../lib/api";
  import type { ReorderPlacement } from "../lib/ui";
  import type { AppView } from "../lib/navigation";

  import { ownValue } from "../lib/settingsMaps";
  import { serviceLabel } from "../lib/ui";

  interface Props {
    activeId: string | null;
    appSettings: AppSettings;
    captureServiceMenuPointer: (event: PointerEvent) => void;
    displayedServiceIcon: (service: Service) => string;
    dragIds: string[];
    dragOverId: string | null;
    dragPlacement: ReorderPlacement | null;
    hibernated: Set<string>;
    markIconFailed: (service: Service) => void;
    onDragEnd: () => void;
    onDragLeave: (e: DragEvent, s: Service) => void;
    onDragOver: (e: DragEvent, s: Service) => void;
    onDragStart: (e: DragEvent, s: Service) => void;
    onDrop: (e: DragEvent, target: Service) => Promise<void>;
    onServiceRowClick: (event: MouseEvent, service: Service) => void;
    openServiceContextMenu: (event: MouseEvent, service: Service) => void;
    openServiceContextMenuFromKeyboard: (event: KeyboardEvent, service: Service) => void;
    serviceDragSelection: string[];
    serviceIconFailed: (service: Service) => boolean;
    serviceIconInverted: (serviceId: string) => boolean;
    serviceOrderBusy: boolean;
    unreadMap: Record<string, number>;
    view: AppView;
    service: Service;
  }

  let {
    activeId,
    appSettings,
    captureServiceMenuPointer,
    displayedServiceIcon,
    dragIds,
    dragOverId,
    dragPlacement,
    hibernated,
    markIconFailed,
    onDragEnd,
    onDragLeave,
    onDragOver,
    onDragStart,
    onDrop,
    onServiceRowClick,
    openServiceContextMenu,
    openServiceContextMenuFromKeyboard,
    serviceDragSelection,
    serviceIconFailed,
    serviceIconInverted,
    serviceOrderBusy,
    unreadMap,
    view,
    service,
  }: Props = $props();

</script>

<div
    class="srow-wrap"
    class:drag-before={appSettings.sidebarServiceDragReorder && !serviceOrderBusy && dragOverId === service.id && dragPlacement === "before"}
    class:drag-after={appSettings.sidebarServiceDragReorder && !serviceOrderBusy && dragOverId === service.id && dragPlacement === "after"}
    class:dragging={appSettings.sidebarServiceDragReorder && !serviceOrderBusy && dragIds.includes(service.id)}
    class:drag-selected={appSettings.sidebarServiceDragReorder && serviceDragSelection.includes(service.id)}
    class:draggable={appSettings.sidebarServiceDragReorder && !serviceOrderBusy}
    draggable={appSettings.sidebarServiceDragReorder && !serviceOrderBusy}
    role="listitem"
    ondragstart={(e) => onDragStart(e, service)}
    ondragover={(e) => onDragOver(e, service)}
    ondragleave={(e) => onDragLeave(e, service)}
    ondrop={(e) => onDrop(e, service)}
    ondragend={onDragEnd}
  >
    <button
      class="srow"
      class:active={service.id === activeId && view === "service"}
      class:disabled={service.isEnabled === false}
      class:asleep={hibernated.has(service.id)}
      aria-disabled={service.isEnabled === false}
      onpointerdown={captureServiceMenuPointer}
      oncontextmenu={(e) => openServiceContextMenu(e, service)}
      onclick={(e) => onServiceRowClick(e, service)}
      onkeydown={(e) => openServiceContextMenuFromKeyboard(e, service)}
      title={`${serviceLabel(service)}${hibernated.has(service.id) ? " · Hibernated" : ""}${(ownValue(unreadMap, service.id) ?? 0) > 0 ? ` · ${ownValue(unreadMap, service.id)} unread` : ""}`}
      aria-label={`${serviceLabel(service)}${hibernated.has(service.id) ? ", hibernated" : ""}${(ownValue(unreadMap, service.id) ?? 0) > 0 ? `, ${ownValue(unreadMap, service.id)} unread` : ""}`}
    >
      {#if serviceIconFailed(service)}
        <span class="dot">{serviceLabel(service).slice(0, 1).toUpperCase()}</span>
      {:else}
        <img class="svc-icon" class:service-icon-inverted={serviceIconInverted(service.id)} src={displayedServiceIcon(service)} alt="" onerror={() => markIconFailed(service)} />
      {/if}
      {#if appSettings.showServiceName && !appSettings.sidebarCollapsed}
        <span class="srow-name">{serviceLabel(service)}</span>
      {/if}
      {#if hibernated.has(service.id) && !appSettings.sidebarCollapsed}<span class="zzz" title="Hibernated">💤</span>{/if}
      {#if service.isBadgeEnabled !== false && (ownValue(unreadMap, service.id) ?? 0) > 0 && (service.isMuted !== true || appSettings.showMessageBadgeWhenMuted)}
        <span class="ubadge" class:muted={service.isMuted === true}>
          {(ownValue(unreadMap, service.id) ?? 0) > 99 ? "99+" : (ownValue(unreadMap, service.id) ?? 0)}
        </span>
      {/if}
    </button>
  </div>

<style>

  button { font-family: inherit; }
  :global(.sidebar.collapsed) .srow-wrap { width: 42px; }
  :global(.sidebar.collapsed) .srow {
    position: relative; width: 42px; height: 42px; min-height: 42px; flex: none;
    justify-content: center; gap: 0; padding: 4px; box-sizing: border-box; border-radius: 8px;
  }
  :global(.sidebar.collapsed) .srow-wrap.drag-before::before, :global(.sidebar.collapsed) .srow-wrap.drag-after::after { left: 4px; right: 4px; }
  :global(.sidebar.collapsed) .ubadge { position: absolute; top: 2px; right: 2px; min-width: 14px; height: 14px; padding: 0 3px; border-radius: 8px; font-size: 9px; line-height: 14px; }

  .srow-wrap { display: flex; align-items: center; position: relative; width: 100%; }
  .srow-wrap.draggable .srow { cursor: grab; }
  .srow-wrap.draggable:active .srow { cursor: grabbing; }
  .srow-wrap.dragging { opacity: 0.42; }
  .srow-wrap.drag-selected .srow:not(.active) { background: color-mix(in srgb, var(--accent) 18%, var(--hover)); outline: 1px solid color-mix(in srgb, var(--accent) 58%, var(--border2)); outline-offset: -1px; }
  .srow-wrap.drag-before::before, .srow-wrap.drag-after::after {
    content: ""; position: absolute; z-index: 2; left: 6px; right: 6px;
    height: 2px; background: var(--accent); border-radius: 2px; pointer-events: none;
  }
  .srow-wrap.drag-before::before { top: -1px; }
  .srow-wrap.drag-after::after { bottom: -1px; }
  .srow { width: 100%;
    display: flex; align-items: center; gap: 9px; flex: 1; min-width: 0;
    padding: 7px 8px; border: none; border-radius: 8px; background: none;
    color: var(--text2); cursor: pointer; text-align: left; font-size: 14px; user-select: none;
  }
  .srow:hover { background: var(--hover); }
  .srow.active { background: var(--accent); color: var(--accent-fg); }
  .srow.disabled { opacity: 0.45; }
  .srow.asleep .svc-icon, .srow.asleep .dot { opacity: 0.5; }
  .zzz { margin-left: auto; font-size: 12px; opacity: 0.8; }
  .svc-icon, .srow .dot { width: var(--icon-size, 22px); height: var(--icon-size, 22px); border-radius: 5px; object-fit: cover; flex: none; }
  .service-icon-inverted { filter: invert(1); }
  .srow.asleep .svc-icon:not(.service-icon-inverted) { filter: grayscale(1); }
  .srow.asleep .svc-icon.service-icon-inverted { filter: invert(1) grayscale(1); }
  .srow .dot { display: grid; place-items: center; background: var(--border2); font-size: 12px; font-weight: 700; }
  .srow-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ubadge {
    margin-left: auto; background: #e23b3b; color: #fff; font-size: 11px; font-weight: 700;
    min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; flex: none;
    display: inline-flex; align-items: center; justify-content: center;
  }
  .ubadge.muted { background: var(--muted2); }

</style>
