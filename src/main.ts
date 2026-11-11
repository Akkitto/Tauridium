import { mount } from "svelte";
import App from "./App.svelte";
import DownloadToast from "./DownloadToast.svelte";
import Titlebar from "./Titlebar.svelte";

declare global {
  interface Window {
    __TAURIDIUM_DOWNLOAD_TOAST__?: boolean;
    __TAURIDIUM_TITLEBAR__?: boolean;
  }
}

const app = mount(window.__TAURIDIUM_TITLEBAR__ ? Titlebar : window.__TAURIDIUM_DOWNLOAD_TOAST__ ? DownloadToast : App, {
  target: document.getElementById("app")!,
});

export default app;
