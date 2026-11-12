// Per-service spell check switch for engines with no native on/off control
// (WebView2 and WKWebView). Forces spellcheck="false" on editable elements while
// disabled and restores each element's own attribute when re-enabled.
(() => {
  const state = window.__tauridiumSpellcheckState;
  if (!state || window.__tauridiumSpellcheckSet) return;
  const MARK = "data-tauridium-spellcheck";
  const EDITABLE = "textarea, input:not([type]), input[type=text], input[type=search], input[type=email], input[type=url], [contenteditable]:not([contenteditable=false])";

  function force(element) {
    if (!(element instanceof Element) || element.hasAttribute(MARK)) return;
    element.setAttribute(MARK, element.getAttribute("spellcheck") ?? "");
    element.setAttribute("spellcheck", "false");
  }

  function restore(element) {
    if (!element.hasAttribute(MARK)) return;
    const original = element.getAttribute(MARK);
    element.removeAttribute(MARK);
    if (original === "") element.removeAttribute("spellcheck");
    else element.setAttribute("spellcheck", original);
  }

  function editableTarget(node) {
    return node instanceof Element ? node.closest(EDITABLE) : null;
  }

  function apply() {
    for (const element of document.querySelectorAll(EDITABLE)) {
      if (state.enabled) restore(element);
      else force(element);
    }
  }

  document.addEventListener("focusin", (event) => {
    if (state.enabled) return;
    const target = editableTarget(event.target);
    if (target) force(target);
  }, true);

  window.__tauridiumSpellcheckSet = (enabled) => {
    state.enabled = Boolean(enabled);
    apply();
  };

  if (!state.enabled) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", apply, { once: true });
    else apply();
  }
})();
