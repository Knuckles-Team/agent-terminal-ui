use crate::{
    ArboraClient, MAX_RESPONSE_BYTES, TaskSnapshot, correlation::TaskCorrelation,
    parse_task_snapshot,
};
use std::time::Duration;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ReadFailure {
    Recoverable,
    Refused,
    Invalid(&'static str),
}

impl ReadFailure {
    pub fn message(self) -> &'static str {
        match self {
            Self::Recoverable => {
                "Arbora read interrupted. Recovery exhausted; press r to retry the read."
            }
            Self::Refused => "Arbora task read refused or unavailable",
            Self::Invalid(message) => message,
        }
    }
}

impl ArboraClient {
    pub async fn read_task(
        &self,
        task_id: &str,
        binding: Option<&TaskCorrelation>,
    ) -> Result<TaskSnapshot, ReadFailure> {
        if task_id.trim().is_empty()
            || task_id.chars().count() > 80
            || task_id.chars().any(char::is_control)
        {
            return Err(ReadFailure::Invalid("Invalid task identifier"));
        }
        if binding.is_some_and(|bound| bound.task_id() != task_id) {
            return Err(ReadFailure::Invalid("Task correlation mismatch"));
        }
        tokio::time::timeout(Duration::from_secs(12), async {
            for attempt in 0..3 {
                let result = self.read_task_once(task_id, binding).await;
                if result != Err(ReadFailure::Recoverable) || attempt == 2 {
                    return result;
                }
                tokio::time::sleep(Duration::from_millis(100 << attempt)).await;
            }
            unreachable!()
        })
        .await
        .unwrap_or(Err(ReadFailure::Recoverable))
    }

    async fn read_task_once(
        &self,
        task_id: &str,
        binding: Option<&TaskCorrelation>,
    ) -> Result<TaskSnapshot, ReadFailure> {
        let mut url = self.card_url.clone();
        url.set_path("/a2a");
        let mut params = serde_json::json!({"id": task_id});
        if self.committed_event_reads {
            params["includeCommittedEvent"] = serde_json::Value::Bool(true);
        }
        let mut response = self
            .http
            .post(url)
            .json(&serde_json::json!({
                "jsonrpc": "2.0", "id": "task-snapshot",
                "method": "tasks/get", "params": params,
            }))
            .send()
            .await
            .map_err(|_| ReadFailure::Recoverable)?;
        if matches!(response.status().as_u16(), 502..=504) {
            return Err(ReadFailure::Recoverable);
        }
        if !response.status().is_success() {
            return Err(ReadFailure::Refused);
        }
        let mut bytes = Vec::new();
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|_| ReadFailure::Recoverable)?
        {
            if chunk.len() > MAX_RESPONSE_BYTES.saturating_sub(bytes.len()) {
                return Err(ReadFailure::Invalid(
                    "Arbora task snapshot exceeds size limit",
                ));
            }
            bytes.extend_from_slice(&chunk);
        }
        let envelope: serde_json::Value = serde_json::from_slice(&bytes)
            .map_err(|_| ReadFailure::Invalid("Invalid Arbora task response"))?;
        if envelope.get("jsonrpc").and_then(|v| v.as_str()) != Some("2.0")
            || envelope.get("id").and_then(|v| v.as_str()) != Some("task-snapshot")
        {
            return Err(ReadFailure::Invalid("Invalid Arbora task response"));
        }
        if envelope.get("error").is_some() {
            return Err(ReadFailure::Refused);
        }
        let mut snapshot =
            parse_task_snapshot(task_id, "task-snapshot", &bytes).map_err(ReadFailure::Invalid)?;
        if let Some(binding) = binding {
            if binding.run_id() != snapshot.correlation.run_id() {
                return Err(ReadFailure::Invalid("Task correlation mismatch"));
            }
            binding
                .validate_binding(&snapshot.correlation)
                .map_err(ReadFailure::Invalid)?;
            snapshot
                .terminal_event
                .validate_binding(binding)
                .map_err(ReadFailure::Invalid)?;
            snapshot.correlation = binding.clone();
        }
        Ok(snapshot)
    }
}
