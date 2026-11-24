<script lang="ts">

  import SupportInformation from "./SupportInformation.svelte";
  import type { AppMetadata } from "../lib/api";
  import tauridiumLogo from "../assets/tauridium.svg";

  interface Props {
    appMetadata: AppMetadata | null;
    appVer: string;
    openProjectLink: (url: string) => Promise<void>;
    projectRepository: string;
  }

  let {
    appMetadata,
    appVer,
    openProjectLink,
    projectRepository,
  }: Props = $props();

</script>

<section class="about-page" aria-labelledby="about-tauridium-title">
                <div class="about-hero">
                  <img class="about-logo" src={tauridiumLogo} alt="Tauridium application icon" />
                  <div class="about-identity"><h3 id="about-tauridium-title">{appMetadata?.name ?? "Tauridium"}</h3><p class="about-version">Version {appVer ? `v${appVer}` : "loading…"}</p><p class="about-summary">{appMetadata?.description ?? "Tauridium desktop client"}</p></div>
                </div>
                <div class="about-actions" role="group" aria-label="Tauridium project links">
                  <button class="primary" onclick={() => openProjectLink(projectRepository)}>Source code ↗</button>
                  <button class="secondary" onclick={() => openProjectLink(`${projectRepository}/releases`)}>Releases ↗</button>
                  <button class="secondary" onclick={() => openProjectLink(`${projectRepository}/issues/new`)}>Report an issue ↗</button>
                </div>
                <SupportInformation />
                <section class="settings-section" aria-labelledby="about-project-heading">
                  <div class="section-heading"><h3 id="about-project-heading">Project</h3><p>Open-source project information and useful destinations.</p></div>
                  <div class="settings-list">
                    <button class="setting-card about-link-card" onclick={() => openProjectLink(projectRepository)}><span class="setting-copy"><span class="setting-label">Repository</span><span class="setting-description">{projectRepository}</span></span><span class="external-indicator" aria-hidden="true">Open ↗</span></button>
                    <button class="setting-card about-link-card" onclick={() => openProjectLink(`${projectRepository}/issues`)}><span class="setting-copy"><span class="setting-label">Issues and feature requests</span><span class="setting-description">Report a problem, follow known issues, or propose an improvement.</span></span><span class="external-indicator" aria-hidden="true">Open ↗</span></button>
                  </div>
                </section>
                <section class="settings-section" aria-labelledby="about-legal-heading">
                  <div class="section-heading"><h3 id="about-legal-heading">Legal</h3></div>
                  <div class="settings-list"><button class="setting-card about-link-card" onclick={() => openProjectLink(`${projectRepository}/blob/master/LICENSE`)}><span class="setting-copy"><span class="setting-label">{appMetadata?.license ?? "License"}</span><span class="setting-description">Copyright © 2026 {appMetadata?.author ?? "Daniel Braniewski"}. View the complete license text.</span></span><span class="external-indicator" aria-hidden="true">View ↗</span></button></div>
                </section>
                <section class="settings-section" aria-labelledby="about-author-heading">
                  <div class="section-heading"><h3 id="about-author-heading">Author</h3></div>
                  <div class="settings-list"><button class="setting-card about-link-card" onclick={() => openProjectLink("https://brani.dev")}><span class="setting-copy"><span class="setting-label">{appMetadata?.author ?? "Daniel Braniewski"}</span><span class="setting-description">brani.dev</span></span><span class="external-indicator" aria-hidden="true">Homepage ↗</span></button></div>
                </section>
                <section class="settings-section" aria-labelledby="about-technology-heading">
                  <div class="section-heading"><h3 id="about-technology-heading">Technology</h3><p>Key projects Tauridium builds on or interoperates with.</p></div>
                  <div class="about-reference-grid">
                    <button class="reference-card" onclick={() => openProjectLink("https://v2.tauri.app/") }><strong>Tauri v2</strong><span>Native desktop application framework ↗</span></button>
                    <button class="reference-card" onclick={() => openProjectLink("https://ferdium.org/") }><strong>Ferdium</strong><span>Service and recipe ecosystem ↗</span></button>
                  </div>
                </section>
              </section>

<style>

  button { font-family: inherit; }
  .primary {
    padding: 10px 14px; border: none; border-radius: 8px; background: var(--accent);
    color: var(--accent-fg); font-weight: 700; cursor: pointer;
  }
  .primary:disabled { opacity: 0.6; cursor: default; }
  .secondary { padding: 9px 12px; border: 1px solid var(--border2); border-radius: 8px; background: var(--input); color: var(--text2); font-weight: 600; cursor: pointer; }
  .secondary:hover { background: var(--hover); border-color: var(--accent); }
  .secondary:disabled { opacity: 0.55; cursor: default; }
  .setting-card:focus-visible, .reference-card:focus-visible, .primary:focus-visible, .secondary:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
  }
  .settings-section { display: flex; flex-direction: column; gap: 10px; }
  .section-heading { display: flex; flex-direction: column; gap: 4px; padding: 0 2px; }
  .section-heading h3 { margin: 0; font-size: 13px; line-height: 1.3; font-weight: 700; color: var(--text); }
  .section-heading p { margin: 0; max-width: 840px; color: var(--muted); font-size: 12.5px; line-height: 1.45; }
  .settings-list { display: flex; flex-direction: column; gap: 8px; }
  .setting-card {
    width: 100%; box-sizing: border-box; display: grid; grid-template-columns: minmax(0, 1fr) auto;
    align-items: center; gap: 18px; min-height: 68px; padding: 13px 14px;
    border: 1px solid var(--border); border-radius: 10px; background: var(--input);
    color: var(--text); text-align: left; font: inherit;
  }
  button.setting-card { cursor: pointer; }
  button.setting-card:hover { background: var(--hover); border-color: var(--border2); }
  .setting-copy { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .setting-label { color: var(--text2); font-size: 14px; line-height: 1.35; font-weight: 650; }
  .setting-description { max-width: 760px; color: var(--muted); font-size: 12.5px; line-height: 1.45; font-weight: 400; }
  :global(.settings-panel) .primary, :global(.settings-panel) .secondary { min-height: 34px; display: inline-flex; align-items: center; justify-content: center; }

  .about-page { display: flex; flex-direction: column; gap: 26px; }
  .about-hero { display: grid; grid-template-columns: 88px minmax(0, 1fr); align-items: center; gap: 20px; padding: 4px 2px 2px; }
  .about-logo { width: 88px; height: 88px; display: block; border-radius: 20px; }
  .about-identity { min-width: 0; }
  .about-identity h3 { margin: 0; color: var(--text); font-size: 26px; line-height: 1.15; letter-spacing: -0.01em; }
  .about-version { margin: 5px 0 0; color: var(--text2); font-size: 13px; font-weight: 650; }
  .about-summary { margin: 8px 0 0; max-width: 560px; color: var(--muted); font-size: 13px; line-height: 1.5; }
  .about-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .about-link-card { appearance: none; }
  .external-indicator { color: var(--muted); font-size: 12px; font-weight: 650; white-space: nowrap; }
  .about-reference-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .reference-card { display: flex; flex-direction: column; gap: 4px; padding: 13px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--input); color: var(--text); text-align: left; cursor: pointer; font: inherit; }
  .reference-card:hover { background: var(--hover); border-color: var(--border2); }
  .reference-card strong { font-size: 14px; }
  .reference-card span { color: var(--muted); font-size: 12px; line-height: 1.4; }
  @media (max-width: 760px) {
    .setting-card { grid-template-columns: 1fr; gap: 10px; align-items: stretch; }
    .about-hero { grid-template-columns: 64px minmax(0, 1fr); gap: 14px; }
    .about-logo { width: 64px; height: 64px; border-radius: 15px; }
    .about-identity h3 { font-size: 22px; }
    .about-reference-grid { grid-template-columns: 1fr; }
  }

</style>
