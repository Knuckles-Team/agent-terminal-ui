pub mod acp;
pub mod coding_approval;
pub mod correlation;
pub mod execution_graph;
pub mod host_logs;
pub mod app {
    pub use crate::host_logs::{HostLaunchReceipt, HostLogReader, run_host_terminal};
}
pub mod public_run_events;
pub mod recovery;
pub mod run_inspector;
pub mod run_inspector_client;
pub mod task_output;
pub mod task_stream;
pub mod terminal_event;
pub mod turn_usage;

use correlation::{TaskCorrelation, TaskEvent, TaskState};
use reqwest::{Client, Url, header};
use std::time::Duration;

const MAX_RESPONSE_BYTES: usize = 1024 * 1024;
pub const SUBMISSION_UNKNOWN: &str = "Submission outcome unknown. It will not be resubmitted. No task identifier is available to refresh.";

pub struct TaskSubmission {
    prompt: String,
    message_id: String,
}

impl TaskSubmission {
    pub fn new(prompt: &str) -> Result<Self, &'static str> {
        if prompt.trim().is_empty() || prompt.len() > 65_536 {
            return Err("Prompt must contain text and be at most 65536 bytes");
        }
        let mut identity = [0_u8; 16];
        getrandom::getrandom(&mut identity).map_err(|_| "Cannot generate submission identity")?;
        let message_id = identity.iter().map(|byte| format!("{byte:02x}")).collect();
        Ok(Self {
            prompt: prompt.to_owned(),
            message_id,
        })
    }

    pub fn message_id(&self) -> &str {
        &self.message_id
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TaskSnapshot {
    pub correlation: TaskCorrelation,
    pub state: TaskState,
    pub terminal_event: terminal_event::TerminalEvent,
    pub output: task_output::TaskOutput,
    pub usage: turn_usage::TurnUsage,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum AuthMode {
    #[default]
    Bearer,
    None,
}

impl AuthMode {
    pub fn parse(value: Option<&str>) -> Result<Self, &'static str> {
        match value {
            None | Some("bearer") => Ok(Self::Bearer),
            Some("none") => Ok(Self::None),
            _ => Err("AGENT_AUTH_MODE must be bearer or none"),
        }
    }
}

pub struct ArboraClient {
    http: Client,
    card_url: Url,
    authenticated: bool,
    auth_mode: AuthMode,
    submission_timeout: Duration,
    committed_event_reads: bool,
}

impl ArboraClient {
    pub fn new(endpoint: &str, token: Option<&str>) -> Result<Self, &'static str> {
        Self::with_auth_mode(endpoint, token, AuthMode::Bearer)
    }

    pub fn with_auth_mode(
        endpoint: &str,
        token: Option<&str>,
        auth_mode: AuthMode,
    ) -> Result<Self, &'static str> {
        if auth_mode == AuthMode::None && token.is_some() {
            return Err("Anonymous mode cannot use a caller credential");
        }
        if endpoint
            .chars()
            .any(|c| c.is_whitespace() || c.is_control() || c == '\\')
        {
            return Err("Invalid Arbora endpoint");
        }
        let mut url = Url::parse(endpoint).map_err(|_| "Invalid Arbora endpoint")?;
        if !matches!(url.scheme(), "http" | "https")
            || url.host_str().is_none()
            || !url.username().is_empty()
            || url.password().is_some()
            || url.query().is_some()
            || url.fragment().is_some()
            || url.path() != "/"
            || url.port() == Some(0)
        {
            return Err("Invalid Arbora endpoint");
        }
        let local = matches!(url.host_str(), Some("localhost" | "127.0.0.1" | "[::1]"));
        if auth_mode == AuthMode::None && !local {
            return Err("Anonymous Arbora requires a loopback endpoint");
        }
        if !local && url.scheme() != "https" {
            return Err("Remote Arbora requires TLS");
        }
        if !local && token.is_none() {
            return Err("Remote Arbora requires a caller credential");
        }
        let mut headers = header::HeaderMap::new();
        if let Some(token) = token {
            if token.is_empty() || !token.bytes().all(|c| (33..=126).contains(&c)) {
                return Err("Invalid caller credential");
            }
            let mut value = header::HeaderValue::from_str(&format!("Bearer {token}"))
                .map_err(|_| "Invalid caller credential")?;
            value.set_sensitive(true);
            headers.insert(header::AUTHORIZATION, value);
        }
        url.set_path("/.well-known/agent-card.json");
        let mut builder = Client::builder();
        if auth_mode == AuthMode::None {
            builder = builder
                .no_proxy()
                .resolve("localhost", std::net::SocketAddr::from(([127, 0, 0, 1], 0)));
        }
        let http = builder
            .default_headers(headers)
            .redirect(reqwest::redirect::Policy::none())
            .retry(reqwest::retry::never())
            .timeout(Duration::from_secs(10))
            .build()
            .map_err(|_| "Cannot initialize Arbora transport")?;
        Ok(Self {
            http,
            card_url: url,
            authenticated: token.is_some(),
            auth_mode,
            submission_timeout: Duration::from_secs(300),
            committed_event_reads: false,
        })
    }

    pub fn with_submission_timeout(mut self, timeout: Duration) -> Result<Self, &'static str> {
        if !(1..=900).contains(&timeout.as_secs()) || timeout.subsec_nanos() != 0 {
            return Err("Submission timeout must be whole seconds between 1 and 900");
        }
        self.submission_timeout = timeout;
        Ok(self)
    }

    pub fn endpoint(&self) -> String {
        let mut endpoint = self.card_url.clone();
        endpoint.set_path("/");
        endpoint.to_string()
    }

    pub fn with_committed_event_reads(mut self, enabled: bool) -> Self {
        self.committed_event_reads = enabled;
        self
    }

    pub async fn submit_task(
        &self,
        submission: &TaskSubmission,
    ) -> Result<TaskSnapshot, &'static str> {
        if !self.authenticated && self.auth_mode != AuthMode::None {
            return Err("Submission requires a caller credential");
        }
        let mut url = self.card_url.clone();
        url.set_path("/a2a");
        let response = self
            .http
            .post(url)
            .timeout(self.submission_timeout)
            .header("Idempotency-Key", submission.message_id())
            .json(&serde_json::json!({
                "jsonrpc": "2.0",
                "id": submission.message_id(),
                "method": "message/send",
                "params": {"configuration": {"blocking": false}, "message": {
                    "kind": "message", "role": "user",
                    "messageId": submission.message_id(),
                    "parts": [{"kind": "text", "text": submission.prompt}],
                }},
            }))
            .send()
            .await
            .map_err(|_| SUBMISSION_UNKNOWN)?;
        if !response.status().is_success() {
            return Err(SUBMISSION_UNKNOWN);
        }
        let bytes = read_task_response(response)
            .await
            .map_err(|_| SUBMISSION_UNKNOWN)?;
        parse_returned_task(submission.message_id(), &bytes).map_err(|_| SUBMISSION_UNKNOWN)
    }

    pub async fn get_task(&self, task_id: &str) -> Result<TaskSnapshot, &'static str> {
        self.read_task(task_id, None)
            .await
            .map_err(|error| error.message())
    }

    pub async fn refresh_task(
        &self,
        binding: &TaskCorrelation,
    ) -> Result<TaskSnapshot, &'static str> {
        self.read_task(binding.task_id(), Some(binding))
            .await
            .map_err(|error| error.message())
    }

    pub async fn cancel_task(
        &self,
        binding: &TaskCorrelation,
    ) -> Result<TaskSnapshot, &'static str> {
        if binding.task_id().chars().count() > 80 {
            return Err("Invalid task identifier");
        }
        let mut url = self.card_url.clone();
        url.set_path("/a2a");
        let response = self
            .http
            .post(url)
            .json(&serde_json::json!({
                "jsonrpc": "2.0",
                "id": "task-cancel",
                "method": "tasks/cancel",
                "params": {"id": binding.task_id()},
            }))
            .send()
            .await
            .map_err(|_| "Arbora cancellation outcome unknown")?;
        if !response.status().is_success() {
            return Err("Arbora cancellation refused or unavailable");
        }
        let bytes = read_task_response(response).await?;
        let task = parse_task_snapshot(binding.task_id(), "task-cancel", &bytes)?;
        binding.validate_binding(&task.correlation)?;
        if task.state != TaskState::Canceled {
            return Err("Arbora cancellation not acknowledged");
        }
        Ok(TaskSnapshot {
            correlation: binding.clone(),
            state: task.state,
            terminal_event: terminal_event::TerminalEvent::default(),
            output: task_output::TaskOutput::default(),
            usage: turn_usage::TurnUsage::default(),
        })
    }

    pub async fn discover(&self) -> Result<String, &'static str> {
        let mut response = self
            .http
            .get(self.card_url.clone())
            .send()
            .await
            .map_err(|_| "Arbora discovery failed or timed out")?;
        if !response.status().is_success() {
            return Err("Arbora discovery refused or unavailable");
        }
        let mut bytes = Vec::new();
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|_| "Arbora response interrupted")?
        {
            if chunk.len() > MAX_RESPONSE_BYTES.saturating_sub(bytes.len()) {
                return Err("Arbora Agent Card exceeds size limit");
            }
            bytes.extend_from_slice(&chunk);
        }
        let card: serde_json::Value =
            serde_json::from_slice(&bytes).map_err(|_| "Invalid Arbora Agent Card")?;
        let name = card
            .get("name")
            .and_then(|v| v.as_str())
            .filter(|name| !name.trim().is_empty())
            .ok_or("Arbora Agent Card has no name")?;
        Ok(name.chars().filter(|c| !c.is_control()).take(80).collect())
    }
}

async fn read_task_response(mut response: reqwest::Response) -> Result<Vec<u8>, &'static str> {
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| "Arbora response interrupted")?
    {
        if chunk.len() > MAX_RESPONSE_BYTES.saturating_sub(bytes.len()) {
            return Err("Arbora task snapshot exceeds size limit");
        }
        bytes.extend_from_slice(&chunk);
    }
    Ok(bytes)
}

fn parse_task_snapshot(
    task_id: &str,
    request_id: &str,
    bytes: &[u8],
) -> Result<TaskSnapshot, &'static str> {
    let snapshot = parse_returned_task(request_id, bytes)?;
    if snapshot.correlation.task_id() != task_id {
        return Err("Task correlation mismatch");
    }
    Ok(snapshot)
}

fn parse_returned_task(request_id: &str, bytes: &[u8]) -> Result<TaskSnapshot, &'static str> {
    let envelope: serde_json::Value =
        serde_json::from_slice(bytes).map_err(|_| "Invalid Arbora task response")?;
    if envelope.get("jsonrpc").and_then(|v| v.as_str()) != Some("2.0")
        || envelope.get("id").and_then(|v| v.as_str()) != Some(request_id)
        || envelope.get("error").is_some()
    {
        return Err("Invalid or refused Arbora task response");
    }
    let task = envelope
        .get("result")
        .ok_or("Missing Arbora task snapshot")?;
    let correlation = TaskCorrelation::from_task(task)?;
    let TaskEvent::Status { state, .. } = correlation.validate(task)? else {
        return Err("Invalid Arbora task snapshot");
    };
    let terminal_event = if request_id == "task-snapshot" {
        terminal_event::TerminalEvent::from_task(task, &correlation, state)?
    } else {
        terminal_event::TerminalEvent::default()
    };
    let output = task_output::TaskOutput::from_task(task, state)?;
    let usage = turn_usage::TurnUsage::from_task(task, &correlation);
    Ok(TaskSnapshot {
        usage,
        output,
        correlation,
        state,
        terminal_event,
    })
}
