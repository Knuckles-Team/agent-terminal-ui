use serde_json::Value;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TaskCorrelation {
    task_id: String,
    context_id: String,
    run_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TaskEvent {
    Status { state: TaskState, final_event: bool },
    Text(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TaskState {
    Submitted,
    Working,
    InputRequired,
    AuthRequired,
    Completed,
    Canceled,
    Failed,
    Rejected,
}

fn identifier<'a>(value: &'a Value, key: &str) -> Result<&'a str, &'static str> {
    value
        .get(key)
        .and_then(Value::as_str)
        .filter(|id| !id.trim().is_empty() && !id.chars().any(char::is_control))
        .ok_or("Missing or invalid task correlation")
}

fn run_id(value: &Value) -> Result<Option<&str>, &'static str> {
    let Some(metadata) = value.get("metadata") else {
        return Ok(None);
    };
    let metadata = metadata.as_object().ok_or("Invalid task metadata")?;
    let Some(graph_os) = metadata.get("graphOs") else {
        return Ok(None);
    };
    let graph_os = graph_os.as_object().ok_or("Invalid GraphOS metadata")?;
    match graph_os.get("runId") {
        None => Ok(None),
        Some(value) => value
            .as_str()
            .filter(|id| !id.trim().is_empty() && !id.chars().any(char::is_control))
            .map(Some)
            .ok_or("Invalid run identifier"),
    }
}

impl TaskCorrelation {
    pub fn from_task(value: &Value) -> Result<Self, &'static str> {
        if value.get("kind").and_then(Value::as_str) != Some("task") {
            return Err("Initial event must be a task");
        }
        let binding = Self {
            task_id: identifier(value, "id")?.to_owned(),
            context_id: identifier(value, "contextId")?.to_owned(),
            run_id: run_id(value)?.map(str::to_owned),
        };
        binding.validate(value)?;
        Ok(binding)
    }

    pub fn task_id(&self) -> &str {
        &self.task_id
    }
    pub fn context_id(&self) -> &str {
        &self.context_id
    }
    pub fn run_id(&self) -> Option<&str> {
        self.run_id.as_deref()
    }

    pub fn validate_binding(&self, other: &Self) -> Result<(), &'static str> {
        self.validate_binding_values(other.task_id(), other.context_id(), other.run_id())
    }

    fn validate_binding_values(
        &self,
        task_id: &str,
        context_id: &str,
        run_id: Option<&str>,
    ) -> Result<(), &'static str> {
        if task_id != self.task_id
            || context_id != self.context_id
            || run_id.is_some_and(|run| Some(run) != self.run_id.as_deref())
        {
            return Err("Task correlation mismatch");
        }
        Ok(())
    }

    pub fn validate(&self, value: &Value) -> Result<TaskEvent, &'static str> {
        let kind = identifier(value, "kind")?;
        let task_key = match kind {
            "task" => "id",
            "status-update" | "artifact-update" => "taskId",
            _ => return Err("Unsupported task event"),
        };
        self.validate_identifiers(value, task_key)?;
        match kind {
            "task" | "status-update" => status_event(value),
            "artifact-update" => artifact_event(value),
            _ => Err("Unsupported task event"),
        }
    }

    fn validate_identifiers(&self, value: &Value, task_key: &str) -> Result<(), &'static str> {
        self.validate_binding_values(
            identifier(value, task_key)?,
            identifier(value, "contextId")?,
            run_id(value)?,
        )?;
        // Reject conflicting aliases instead of selecting the first identifier.
        if value.get("id").is_some() && identifier(value, "id")? != self.task_id {
            return Err("Task correlation mismatch");
        }
        if value.get("taskId").is_some() && identifier(value, "taskId")? != self.task_id {
            return Err("Task correlation mismatch");
        }
        Ok(())
    }
}

fn task_state(value: &Value) -> Result<TaskState, &'static str> {
    Ok(
        match value.pointer("/status/state").and_then(Value::as_str) {
            Some("submitted") => TaskState::Submitted,
            Some("working") => TaskState::Working,
            Some("input-required") => TaskState::InputRequired,
            Some("auth-required") => TaskState::AuthRequired,
            Some("completed") => TaskState::Completed,
            Some("canceled") => TaskState::Canceled,
            Some("failed") => TaskState::Failed,
            Some("rejected") => TaskState::Rejected,
            _ => return Err("Unsupported task state"),
        },
    )
}

fn status_event(value: &Value) -> Result<TaskEvent, &'static str> {
    let state = task_state(value)?;
    let terminal = matches!(
        state,
        TaskState::Completed | TaskState::Canceled | TaskState::Failed | TaskState::Rejected
    );
    let final_event = match value.get("final") {
        None => terminal,
        Some(value) => value.as_bool().ok_or("Invalid final flag")? && terminal,
    };
    Ok(TaskEvent::Status { state, final_event })
}

fn artifact_event(value: &Value) -> Result<TaskEvent, &'static str> {
    let parts = value
        .pointer("/artifact/parts")
        .and_then(Value::as_array)
        .filter(|parts| !parts.is_empty())
        .ok_or("Invalid text artifact")?;
    let mut text = String::new();
    for part in parts {
        if part.get("kind").and_then(Value::as_str) != Some("text") {
            return Err("Unsupported artifact part");
        }
        text.push_str(
            part.get("text")
                .and_then(Value::as_str)
                .ok_or("Invalid text artifact")?,
        );
    }
    Ok(TaskEvent::Text(text))
}
