import { mount } from "svelte";
import App from "./App.svelte";
import DownloadToast from "./DownloadToast.svelte";
import Titlebar from "./Titlebar.svelte";
import ServiceMenu from "./ServiceMenu.svelte";

declare global {
  interface Window {
    __TAURIDIUM_DOWNLOAD_TOAST__?: boolean;
    __TAURIDIUM_TITLEBAR__?: boolean;
    __TAURIDIUM_SERVICE_MENU__?: boolean;
    __TAURIDIUM_SERVICE_MENU_OPAQUE__?: boolean;
  }
}

const app = mount(window.__TAURIDIUM_SERVICE_MENU__ ? ServiceMenu : window.__TAURIDIUM_TITLEBAR__ ? Titlebar : window.__TAURIDIUM_DOWNLOAD_TOAST__ ? DownloadToast : App, {
  target: document.getElementById("app")!,
});

export default app;
