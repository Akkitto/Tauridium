<script lang="ts">

  import type { RecipeDraft, RecipePreview, RecipeStorageInfo } from "../lib/api";
  import type { AddServiceMode as AddMode } from "../lib/navigation";
  import { recipeSourceLabel } from "../lib/ui";

  interface Props {
    addMode: AddMode;
    allRecipes: RecipePreview[];
    backToService: () => void;
    createWebsite: () => Promise<void>;
    customRecipes: RecipePreview[];
    customWebsiteUrl: string;
    error: string | null;
    filteredRecipes: RecipePreview[];
    importRecipe: (directory: boolean) => Promise<void>;
    newServiceName: string;
    openCustomWebsite: (prefill?: string) => void;
    openRecipeCreator: () => void;
    pickRecipe: (r: RecipePreview) => Promise<void>;
    recipeAdvanced: boolean;
    recipeDraft: RecipeDraft;
    recipeIdEdited: boolean;
    recipeQuery: string;
    recipeSaving: boolean;
    recipeStorage: RecipeStorageInfo | null;
    recipesLoading: boolean;
    refreshRecipes: () => Promise<void>;
    saveRecipe: (addService: boolean) => Promise<void>;
    setRecipeName: (name: string) => void;
  }

  let {
    addMode = $bindable(),
    allRecipes,
    backToService,
    createWebsite,
    customRecipes,
    customWebsiteUrl = $bindable(),
    error,
    filteredRecipes,
    importRecipe,
    newServiceName = $bindable(),
    openCustomWebsite,
    openRecipeCreator,
    pickRecipe,
    recipeAdvanced = $bindable(),
    recipeDraft = $bindable(),
    recipeIdEdited = $bindable(),
    recipeQuery = $bindable(),
    recipeSaving,
    recipeStorage,
    recipesLoading,
    refreshRecipes,
    saveRecipe,
    setRecipeName,
  }: Props = $props();

</script>

<div class="panel">
          <div class="panel-head">
            <h2>Add a service</h2>
            <button class="link" onclick={backToService}>✕ close</button>
          </div>
          <p class="notice">⚠️ Passkey / biometric sign-in (Touch ID, security keys) isn't supported in the embedded webview. On a service's login screen, choose "try another way" and use a password + authenticator code (TOTP) or a phone prompt instead.</p>

          <div class="add-tabs" role="tablist" aria-label="Add service method">
            <button class:active={addMode === "catalog"} onclick={() => (addMode = "catalog")}>Recipes</button>
            <button class:active={addMode === "website"} onclick={() => openCustomWebsite()}>Custom website</button>
            <button class:active={addMode === "creator"} onclick={openRecipeCreator}>Recipe creator</button>
          </div>

          {#if error}<p class="error">{error}</p>{/if}

          {#if addMode === "catalog"}
            <label class="block">
              Name (optional)
              <input bind:value={newServiceName} placeholder="leave empty = recipe name" />
            </label>
            <input class="filter" bind:value={recipeQuery} placeholder="Filter among {allRecipes.length} services…" />
            <div class="recipe-tools">
              <button class="secondary sm" onclick={refreshRecipes} disabled={recipesLoading}>Refresh</button>
              <button class="secondary sm" onclick={() => importRecipe(true)}>Import folder…</button>
              <button class="secondary sm" onclick={() => importRecipe(false)}>Import package.json…</button>
            </div>
            {#if recipeStorage}
              <p class="recipe-path">Personal recipe folder: <code>{recipeStorage.recipesDir}</code></p>
            {/if}
            {#if recipesLoading}
              <p class="sub">Loading catalog…</p>
            {:else}
              <div class="results">
                {#each filteredRecipes as r (r.id)}
                  <button class="result" onclick={() => pickRecipe(r)}>
                    {#if r.icons?.svg}<img class="result-icon" src={r.icons.svg} alt="" />{/if}
                    <span class="result-main">
                      <span class="result-name">{r.name}</span>
                      {#if r.description}<span class="result-desc">{r.description}</span>{/if}
                    </span>
                    <span class="result-meta">
                      {#if r.source}<span class="source-badge">{recipeSourceLabel(r.source)}</span>{/if}
                      <span class="result-id">{r.id}</span>
                    </span>
                  </button>
                {:else}
                  <div class="empty-recipe">
                    <strong>No preset recipe matches.</strong>
                    <p class="sub">You can still add the site directly or create a reusable personal recipe.</p>
                    <div class="recipe-tools">
                      <button class="primary sm" onclick={() => openCustomWebsite(recipeQuery)}>Add a custom website</button>
                      <button class="secondary sm" onclick={openRecipeCreator}>Create a recipe</button>
                    </div>
                  </div>
                {/each}
              </div>
            {/if}
          {:else if addMode === "website"}
            <div class="creator-card">
              <h3>Custom Website</h3>
              <p class="sub">A one-off service that uses Tauridium’s built-in Custom Website template. It is not a reusable personal recipe, but service export can generate a standalone Ferdium-compatible recipe for it.</p>
              <label class="block">Website URL<input bind:value={customWebsiteUrl} placeholder="https://example.com" /></label>
              <label class="block">Name (optional)<input bind:value={newServiceName} placeholder="derived from the hostname" /></label>
              <div class="recipe-actions">
                <button class="primary" onclick={createWebsite}>Add website</button>
                <button class="secondary" onclick={() => (addMode = "catalog")}>Back to recipes</button>
              </div>
            </div>
          {:else}
            <div class="creator-card">
              <h3>Personal recipe creator</h3>
              <p class="sub">Creates a reusable personal recipe under Tauridium's configuration folder. Name, id, and URL are enough for a basic recipe.</p>
              <div class="creator-grid">
                <label class="block">Recipe name<input value={recipeDraft.name} oninput={(e) => setRecipeName(e.currentTarget.value)} placeholder="My AI Service" /></label>
                <label class="block">Recipe id<input value={recipeDraft.id} oninput={(e) => { recipeIdEdited = true; recipeDraft.id = e.currentTarget.value.toLowerCase(); }} placeholder="my-ai-service" /></label>
              </div>
              <label class="block">Service URL<input bind:value={recipeDraft.serviceUrl} placeholder="https://example.com" /></label>
              <label class="block">Description (optional)<input bind:value={recipeDraft.description} placeholder="What this recipe opens" /></label>
              <div class="creator-options">
                <label class="row-toggle compact"><span>Allow a per-service custom URL</span><input type="checkbox" bind:checked={recipeDraft.hasCustomUrl} /></label>
                <label class="row-toggle compact"><span>Use a teamId placeholder in the URL</span><input type="checkbox" bind:checked={recipeDraft.hasTeamId} /></label>
              </div>
              <button class="link" onclick={() => (recipeAdvanced = !recipeAdvanced)}>{recipeAdvanced ? "Hide advanced files" : "Advanced: icon.svg / webview.js"}</button>
              {#if recipeAdvanced}
                <label class="block">icon.svg (optional)<textarea class="code-input" bind:value={recipeDraft.iconSvg} rows="5" placeholder="<svg …>…</svg>"></textarea></label>
                <label class="block">webview.js (optional)<textarea class="code-input" bind:value={recipeDraft.webviewJs} rows="8" placeholder="Optional Ferdium-compatible recipe integration script"></textarea></label>
                <p class="notice security-note">A recipe webview.js runs inside the loaded website and can access that page's DOM. Only import or write scripts you trust.</p>
              {/if}
              <label class="block">Service name after “Save & add” (optional)<input bind:value={newServiceName} placeholder="leave empty = recipe name" /></label>
              <div class="recipe-actions">
                <button class="primary" disabled={recipeSaving} onclick={() => saveRecipe(true)}>{recipeSaving ? "Saving…" : "Save & add"}</button>
                <button class="secondary" disabled={recipeSaving} onclick={() => saveRecipe(false)}>Save recipe</button>
                <button class="secondary" onclick={() => importRecipe(true)}>Import folder…</button>
              </div>
              {#if recipeStorage}
                <p class="recipe-path">Saved under <code>{recipeStorage.recipesDir}</code> as <code>&lt;recipe-id&gt;/package.json</code>. You can also place compatible recipe folders there manually and press Refresh.</p>
              {/if}
              {#if customRecipes.length > 0}<p class="sub">{customRecipes.length} custom recipe{customRecipes.length === 1 ? "" : "s"} currently loaded.</p>{/if}
            </div>
          {/if}
        </div>

<style>

  button, input, textarea { font-family: inherit; }
  .sub { margin: 0 0 6px; color: var(--muted); font-size: 13px; }
  label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }
  input {
    padding: 9px 11px; border-radius: 8px; border: 1px solid var(--border2);
    background: var(--input); color: var(--text); font-size: 14px;
  }
  .primary {
    padding: 10px 14px; border: none; border-radius: 8px; background: var(--accent);
    color: var(--accent-fg); font-weight: 700; cursor: pointer;
  }
  .primary:disabled { opacity: 0.6; cursor: default; }
  .error { color: #ff8a8a; font-size: 13px; margin: 4px 0; }
  .link { background: none; border: none; color: var(--link); cursor: pointer; font-size: 12px; text-decoration: underline; }
  .panel {
    width: min(560px, 90%); align-self: start; margin: 40px auto;
    background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 22px;
    display: flex; flex-direction: column; gap: 14px;
  }
  .panel-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .primary.sm { padding: 6px 12px; font-size: 13px; }
  .panel-head h2 { margin: 0; font-size: 18px; }
  .row-toggle { flex-direction: row; align-items: center; gap: 10px; color: var(--text2); font-size: 14px; cursor: pointer; }
  .row-toggle input { width: auto; }
  .notice {
    margin: 0; padding: 9px 11px; border-radius: 8px; font-size: 12px; line-height: 1.4;
    background: rgba(217, 119, 6, 0.12); border: 1px solid rgba(217, 119, 6, 0.35); color: var(--text2);
  }
  .block { gap: 6px; }
  .results { display: flex; flex-direction: column; gap: 6px; max-height: 55vh; overflow-y: auto; }
  .result {
    display: flex; justify-content: space-between; align-items: center;
    background: var(--input); border: 1px solid var(--border); border-radius: 8px;
    padding: 9px 11px; cursor: pointer; color: var(--text); text-align: left;
  }
  .result:hover { background: var(--hover); border-color: var(--accent); }
  .result-icon { width: 22px; height: 22px; border-radius: 5px; flex: none; }
  .result-name { flex: 1; }
  .result-id { color: var(--muted2); font-size: 12px; }
  .secondary { padding: 9px 12px; border: 1px solid var(--border2); border-radius: 8px; background: var(--input); color: var(--text2); font-weight: 600; cursor: pointer; }
  .secondary:hover { background: var(--hover); border-color: var(--accent); }
  .secondary:disabled { opacity: 0.55; cursor: default; }
  .secondary.sm { padding: 6px 10px; font-size: 12px; }
  .add-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
  .add-tabs button { padding: 7px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--input); color: var(--muted); cursor: pointer; }
  .add-tabs button.active { border-color: var(--accent); color: var(--text); background: var(--hover); }
  .recipe-tools, .recipe-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .recipe-path { margin: -4px 0 2px; color: var(--muted2); font-size: 11px; line-height: 1.45; word-break: break-all; }
  .result { gap: 10px; }
  .result-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .result-name { font-weight: 600; }
  .result-desc { color: var(--muted); font-size: 11px; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .result-meta { flex: none; display: flex; flex-direction: column; align-items: flex-end; gap: 3px; }
  .source-badge { padding: 2px 6px; border-radius: 999px; background: var(--hover); color: var(--accent-soft); font-size: 10px; font-weight: 700; letter-spacing: 0.02em; }
  .empty-recipe { padding: 14px; border: 1px dashed var(--border2); border-radius: 10px; display: flex; flex-direction: column; gap: 8px; }
  .empty-recipe .sub { margin: 0; }
  .creator-card { display: flex; flex-direction: column; gap: 12px; }
  .creator-card h3 { margin: 0; font-size: 16px; }
  .creator-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .creator-options { display: flex; flex-direction: column; gap: 6px; }
  .row-toggle.compact { flex-direction: row; justify-content: space-between; padding: 7px 9px; border: 1px solid var(--border); border-radius: 8px; background: var(--input); }
  textarea { width: 100%; box-sizing: border-box; resize: vertical; padding: 9px 11px; border-radius: 8px; border: 1px solid var(--border2); background: var(--input); color: var(--text); font-size: 13px; }
  .code-input { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; line-height: 1.4; }
  .security-note { margin-top: -4px; }
  .primary:focus-visible, .secondary:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
  }
  @media (max-width: 760px) {
    .creator-grid { grid-template-columns: 1fr; }
  }

</style>
