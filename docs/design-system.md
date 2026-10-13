# Design system

The app uses a built-in Textual theme. `agent_terminal_ui/app.py` selects it by name, and the default is `tokyo-night`.

The `/theme` command switches the theme at run time. Colours should come from theme variables. Components must not hard-code colour values.

The native discovery client uses the Tokyo Night foreground and background
tokens. `AGENT_THEME` defaults to `tokyo-night`; unsupported names use that same
palette. A nonempty `NO_COLOR` uses the terminal's foreground and background.
Status and keyboard help wrap when the viewport narrows. This discovery slice
does not provide runtime theme switching or complete presentation parity.
