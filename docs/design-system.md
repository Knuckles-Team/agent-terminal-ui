# Design system

The app uses a built-in Textual theme. `agent_terminal_ui/app.py` selects it by name, and the default is `tokyo-night`.

The `/theme` command switches the theme at run time. Colours should come from theme variables. Components must not hard-code colour values.
