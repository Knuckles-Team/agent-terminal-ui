# Design system

The app uses a registered Textual theme. `agent_terminal_ui/app.py` selects it by name, and the default is `tokyo-night`.

The `/theme` command switches the theme at run time. Colours should come from theme variables. Components must not hard-code colour values.

The native client defaults to the Tokyo Night foreground and background
tokens. `AGENT_THEME` defaults to `tokyo-night`; unsupported names use that same
palette. A nonempty `NO_COLOR` uses the terminal's foreground and background.
Status and keyboard help wrap when the viewport narrows. F6 cycles the native palette without changing the active request.
Complete presentation parity remains pending.

The native view also accepts `nord`, `gruvbox` and `textual-light` through
`AGENT_THEME`. The optional `canopy` palette uses dark green and pale stone
foreground/background tokens. Python also registers sage and stone accents.
Set `AGENT_THEME=canopy` to opt in; existing choices and defaults do not change.
Canopy uses opaque colors, not simulated transparency.
The original foreground and background use the Textual built-in baseline;
Textual Light uses its generated foreground. Tests require at least 4.5:1 text
contrast. Status meanings stay in text, including with `NO_COLOR=0` (nonempty).
Native rendering has no animations, so reduced-motion use needs no extra flag.

PageUp and PageDown move one viewport. Home returns to the first row; End
follows the last row. Wrapping uses terminal cell widths. Refresh and resize
retain the requested wrapped row, while the displayed offset is clamped to
available content. A temporary loading message does not discard that position.
The viewport uses Ratatui's bounded 16-bit row offset. No network action is
triggered by these navigation keys.

Canopy and the spatial DAG view are optional presentation additions. In the
native run inspector, `g` opens the validated flat graph. The default view is
the complete step list with dependency and public evidence details. Press `v`
for a map at 72 columns by 20 rows or larger. Left/Right and Up/Down pan;
Tab/Shift+Tab select; Home reveals the selected card. Cards shorten long labels; `v`
returns to full details. Ctrl+F searches the full list. A smaller
terminal uses the list and returns to the map when enough space is available.

Map edges mean `depends_on`, never child creation. Unobserved means unknown,
not pending. The current graph does not provide child transcripts, messaging
or continuation. Refresh clears the old protected graph and selection before
loading; close, refusal and changed authority clear derived map state too.
Map navigation and redraw make no requests and add no animation.
