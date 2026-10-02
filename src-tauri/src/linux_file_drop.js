// WebKitGTK bug 323277: a native file drop can arrive as an empty URI list.
// Keep the hosted page in place and explain the working attachment-picker path.
// This never grants file access or synthesizes files or upload events.
(function () {
  let timer;
  document.addEventListener("drop", function (event) {
    const transfer = event.dataTransfer;
    if (!event.isTrusted || !transfer || transfer.files.length ||
        !Array.from(transfer.types).includes("text/uri-list") ||
        transfer.getData("text/uri-list").trim()) return;

    event.preventDefault();
    const previous = document.getElementById("__tauridium-file-drop-help");
    if (previous) previous.remove();
    clearTimeout(timer);

    const host = document.createElement("div");
    host.id = "__tauridium-file-drop-help";
    host.style.cssText = "position:fixed!important;bottom:24px!important;right:24px!important;z-index:2147483647!important;max-width:min(420px,85vw)!important";
    const root = host.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent = "section{padding:14px 16px;background:#252936;color:#fff;border:1px solid #626879;border-radius:10px;box-shadow:0 4px 16px #0005;font:14px/1.5 system-ui}p{margin:0}button{margin-top:8px;padding:4px 10px;border:1px solid #626879;border-radius:4px;background:transparent;color:inherit;font:inherit;cursor:pointer}";
    const panel = document.createElement("section");
    panel.setAttribute("role", "status");
    const message = document.createElement("p");
    message.textContent = "This Linux browser engine cannot attach dropped files. Use the service's attachment button to choose files instead.";
    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.textContent = "Dismiss";
    dismiss.addEventListener("click", () => { host.remove(); clearTimeout(timer); });
    panel.append(message, dismiss);
    root.append(style, panel);
    (document.body || document.documentElement).append(host);
    timer = setTimeout(() => host.remove(), 10000);
  }, true);
})();
