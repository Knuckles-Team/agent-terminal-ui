# Agent observation

Use `tuig --observe-task TASK_ID` for read-only native observation. Headless
observation uses `tuig --headless --observe-task TASK_ID`. It does not create
a task, approve tools or cancel remote work.

The former Python background-agent dashboard is retired. Native multi-session
management is not supplied by a parallel implementation.
