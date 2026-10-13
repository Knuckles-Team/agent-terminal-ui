pub mod correlation;

use correlation::{TaskCorrelation, TaskEvent, TaskState};
use reqwest::{Client, Url, header};
use std::time::Duration;

const MAX_RESPONSE_BYTES: usize = 1024 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TaskSnapshot {
    pub correlation: TaskCorrelation,
    pub state: TaskState,
}

pub struct GraphOsClient {
    http: Client,
    card_url: Url,
}

impl GraphOsClient {
    pub fn new(endpoint: &str, token: Option<&str>) -> Result<Self, &'static str> {
        if endpoint
            .chars()
            .any(|c| c.is_whitespace() || c.is_control() || c == '\\')
        {
            return Err("Invalid GraphOS endpoint");
        }
        let mut url = Url::parse(endpoint).map_err(|_| "Invalid GraphOS endpoint")?;
        if !matches!(url.scheme(), "http" | "https")
            || url.host_str().is_none()
            || !url.username().is_empty()
            || url.password().is_some()
            || url.query().is_some()
            || url.fragment().is_some()
            || url.path() != "/"
            || url.port() == Some(0)
        {
            return Err("Invalid GraphOS endpoint");
        }
        let local = matches!(url.host_str(), Some("localhost" | "127.0.0.1" | "[::1]"));
        if !local && url.scheme() != "https" {
            return Err("Remote GraphOS requires TLS");
        }
        if !local && token.is_none() {
            return Err("Remote GraphOS requires a caller credential");
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
        let http = Client::builder()
            .default_headers(headers)
            .redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(10))
            .build()
            .map_err(|_| "Cannot initialize GraphOS transport")?;
        Ok(Self {
            http,
            card_url: url,
        })
    }

    pub async fn get_task(&self, task_id: &str) -> Result<TaskSnapshot, &'static str> {
        if task_id.trim().is_empty()
            || task_id.chars().count() > 80
            || task_id.chars().any(char::is_control)
        {
            return Err("Invalid task identifier");
        }
        let mut url = self.card_url.clone();
        url.set_path("/a2a");
        let mut response = self
            .http
            .post(url)
            .json(&serde_json::json!({
                "jsonrpc": "2.0",
                "id": "task-snapshot",
                "method": "tasks/get",
                "params": {"id": task_id},
            }))
            .send()
            .await
            .map_err(|_| "GraphOS task read failed or timed out")?;
        if !response.status().is_success() {
            return Err("GraphOS task read refused or unavailable");
        }
        let mut bytes = Vec::new();
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|_| "GraphOS response interrupted")?
        {
            if chunk.len() > MAX_RESPONSE_BYTES.saturating_sub(bytes.len()) {
                return Err("GraphOS task snapshot exceeds size limit");
            }
            bytes.extend_from_slice(&chunk);
        }
        parse_task_snapshot(task_id, &bytes)
    }

    pub async fn discover(&self) -> Result<String, &'static str> {
        let mut response = self
            .http
            .get(self.card_url.clone())
            .send()
            .await
            .map_err(|_| "GraphOS discovery failed or timed out")?;
        if !response.status().is_success() {
            return Err("GraphOS discovery refused or unavailable");
        }
        let mut bytes = Vec::new();
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|_| "GraphOS response interrupted")?
        {
            if chunk.len() > MAX_RESPONSE_BYTES.saturating_sub(bytes.len()) {
                return Err("GraphOS Agent Card exceeds size limit");
            }
            bytes.extend_from_slice(&chunk);
        }
        let card: serde_json::Value =
            serde_json::from_slice(&bytes).map_err(|_| "Invalid GraphOS Agent Card")?;
        let name = card
            .get("name")
            .and_then(|v| v.as_str())
            .filter(|name| !name.trim().is_empty())
            .ok_or("GraphOS Agent Card has no name")?;
        Ok(name.chars().filter(|c| !c.is_control()).take(80).collect())
    }
}

fn parse_task_snapshot(task_id: &str, bytes: &[u8]) -> Result<TaskSnapshot, &'static str> {
    let envelope: serde_json::Value =
        serde_json::from_slice(bytes).map_err(|_| "Invalid GraphOS task response")?;
    if envelope.get("jsonrpc").and_then(|v| v.as_str()) != Some("2.0")
        || envelope.get("id").and_then(|v| v.as_str()) != Some("task-snapshot")
        || envelope.get("error").is_some()
    {
        return Err("Invalid or refused GraphOS task response");
    }
    let task = envelope
        .get("result")
        .ok_or("Missing GraphOS task snapshot")?;
    let correlation = TaskCorrelation::from_task(task)?;
    if correlation.task_id() != task_id {
        return Err("Task correlation mismatch");
    }
    let TaskEvent::Status { state, .. } = correlation.validate(task)? else {
        return Err("Invalid GraphOS task snapshot");
    };
    Ok(TaskSnapshot { correlation, state })
}
