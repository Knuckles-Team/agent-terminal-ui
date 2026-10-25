# Native features

`--prompt TEXT` submits one text task. `--observe-task TASK_ID` observes without
remote cancellation. Add `--headless` to print unary snapshots without opening
a terminal. These commands share the native Arbora client.

In the terminal, F6 changes theme; `l` opens logs; `i` opens the run inspector;
`r` refreshes; `c` cancels only the local request; `q` or Ctrl+C quits. `x`
requests remote cancellation only after confirmation and is disabled for observers.
Arrow, page and mouse-wheel controls scroll. Tab selects public details and
Enter or Space expands them.

There is no interactive composer or Python slash-command fallback. Streaming,
approval attachment and durable resume remain open requirements.
