# Settings search

Open **Settings** and use **Search settings**, or press **Ctrl+F** (**Cmd+F** on macOS) while Settings is open. Search matches option names, section names and keywords. Each result shows its destination tab.

- Use Up/Down to choose a result and Enter to open it, or click a result.
- Tauridium switches to the correct tab, scrolls to the setting and briefly highlights it. Enabled form controls receive focus. Action groups receive focus without executing their buttons.
- Escape dismisses results while keeping your query. Press Escape again to clear it, or use **Clear settings search**. Tab leaves the result list without choosing anything.
- If an option requires another option first, search points to that prerequisite and explains it. It never enables the prerequisite automatically.
- Unavailable Windows, Flatpak and desktop-tray controls are excluded. Workspace navigation uses the existing unsaved-name confirmation before leaving the workspace editor.
- Shortcut recording keeps priority over Ctrl/Cmd+F; explicitly focusing search cancels recording without changing the binding.

The index contains static UI labels and keywords. It does not index saved values, local paths, service/workspace names, audit events or credentials. Queries stay in the Settings component's memory and are discarded when Settings closes; they are not saved or logged.

The keyboard interaction follows the editable [WAI-ARIA combobox pattern](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/). Navigation uses immediate scrolling and does not require animation.
