# Agent View and execution inspection

## Current scope

`/agents` and the `--bg` startup flag open the Python Agent View screen.
The screen contains session-row and preview components, but production code does
not populate a served session inventory. Its refresh timer redraws supplied rows;
it does not discover running agents.

The Attach and Reply bindings emit a local selection request. They do not open
a child-agent conversation or send a message. `/bg` and `/attach <id>`
report unavailable without changing the active session or starting remote work.
The startup flags `--bg --prompt "task"` do not establish supported background execution.

The Swarm `GraphTree` is an unpopulated presentation component. Production code
does not call `add_agent_node`. Selecting a supplied node opens `ChatModal`, which
displays supplied messages and has no composer or send action. `WorkflowSidebar`
is a flat progress list, not an orchestration dependency graph.

## Expandable public details

Python and native consumers support separate, initially collapsed public model
summary and execution-trace sections when Arbora supplies compatible events.
The Python composer reaches conversation folds with F8, then Tab; Enter or Space
toggles the focused fold. Tool blocks also support keyboard and mouse expansion.
These controls display public projections only, not private model reasoning.
Their availability does not establish a nested-agent inventory or targeted chat.

## Planned execution explorer

The owning [terminal requirements](https://github.com/Knuckles-Team/agent-terminal-ui/blob/main/specs/terminal-runtime/requirements.md)
keep nested inspection and targeted interaction separate:

- Inspect any producer-exposed execution level through a stable node locator
  and ancestor breadcrumbs.
- Select hierarchy or dependency graph nodes, with a keyboard-accessible list
  for narrow terminals.
- Expand authorized public summaries, tool activity and conversation history.
- Message an active child only when the backend supplies its target capability.
- Continue a completed child through a separate, supported continuation action.

These capabilities are not delivered by the existing Agent View components.
A graph node or trace span is not automatically a chat destination. Missing
backend capabilities must remain unavailable, and inspection must not silently
retarget the current conversation.

## Source components

| File | Current role |
|------|--------------|
| `screens/agent_view.py` | Supplied session rows, preview and local selection messages |
| `widgets/graph_tree.py` | Supplied tree-node presentation |
| `tui/chat_modal.py` | Read-only display of supplied messages |
| `widgets/workflow.py` | Flat workflow progress presentation |
| `commands.py` | `/agents` entry and explicit `/bg` and `/attach` refusals |
| `background_runner.py` | Local runner component, not a served child-control contract |
