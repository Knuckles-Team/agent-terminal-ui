# Sessions and state

Task, context and run identifiers are separate opaque server values. The native
client validates their bindings during observation. Reading `AGENT_TASK_ID` or
`--observe-task` does not reload prior turns or resume a conversation.

The former Python SQLite session store, offline queue and workspace snapshots
are retired. Native durable resume and context continuation remain open.
No local store is introduced as a second authority.
