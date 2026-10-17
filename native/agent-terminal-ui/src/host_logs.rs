//! Authenticated, read-only host log transport. Bindings cannot be constructed by callers.
use crate::GraphOsClient;
use serde_json::{Value, json};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub const REFUSED: &str = "Host logs unavailable. Authenticated host access is required.";

pub struct HostLogs {
    reference: String,
    expires: u64,
    cursor: Option<String>,
    client: std::sync::Arc<GraphOsClient>,
}

pub struct LogBatch {
    pub messages: Vec<String>,
    pub gap: bool,
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

fn receipt(value: &Value) -> Result<(String, u64), &'static str> {
    let object = value.as_object().ok_or(REFUSED)?;
    let fields = [
        "log_ref",
        "host_instance",
        "workspace",
        "tenant",
        "principal",
        "session_ref",
        "policy_revision",
        "grant_revision",
    ];
    if object.len() != 13
        || fields.iter().any(|key| {
            value[*key]
                .as_str()
                .is_none_or(|s| s.is_empty() || s.len() > 4096)
        })
        || value["version"].as_u64() != Some(1)
        || value["ready"].as_bool() != Some(true)
        || value["web_logs"].as_bool() != Some(true)
        || !matches!(value["interface_mode"].as_str(), Some("terminal" | "both"))
    {
        return Err(REFUSED);
    }
    let reference = value["log_ref"].as_str().ok_or(REFUSED)?;
    let expires = value["expires_at_ms"].as_u64().ok_or(REFUSED)?;
    if reference.len() > 128 || expires <= now_ms() {
        return Err(REFUSED);
    }
    Ok((reference.to_owned(), expires))
}

async fn post(client: &GraphOsClient, path: &str, body: Value) -> Result<Value, &'static str> {
    if !client.authenticated {
        return Err(REFUSED);
    }
    tokio::time::timeout(Duration::from_secs(1), async {
        let mut url = client.card_url.clone();
        url.set_path(path);
        let mut response = client
            .http
            .post(url)
            .json(&body)
            .send()
            .await
            .map_err(|_| REFUSED)?;
        if !response.status().is_success() {
            return Err(REFUSED);
        }
        let mut bytes = Vec::new();
        while let Some(chunk) = response.chunk().await.map_err(|_| REFUSED)? {
            if bytes.len() + chunk.len() > 2 * 1024 * 1024 {
                return Err(REFUSED);
            }
            bytes.extend_from_slice(&chunk);
        }
        serde_json::from_slice(&bytes).map_err(|_| REFUSED)
    })
    .await
    .map_err(|_| REFUSED)?
}

impl HostLogs {
    pub async fn bind(client: std::sync::Arc<GraphOsClient>) -> Result<Self, &'static str> {
        let value = post(&client, "/host/logs/reference", json!({})).await?;
        let (reference, expires) = receipt(&value)?;
        Ok(Self {
            reference,
            expires,
            cursor: None,
            client,
        })
    }

    pub fn expires_at_ms(&self) -> u64 {
        self.expires
    }

    pub fn unexpired(expires: u64) -> bool {
        expires > now_ms()
    }

    pub fn valid(&self) -> bool {
        self.expires > now_ms()
    }

    pub async fn read(&mut self) -> Result<LogBatch, &'static str> {
        let result = self.read_inner().await;
        if result.is_err() {
            self.expires = 0;
            self.cursor = None;
        }
        result
    }

    async fn read_inner(&mut self) -> Result<LogBatch, &'static str> {
        if !self.valid() {
            return Err(REFUSED);
        }
        let value = post(
            &self.client,
            "/host/logs/read",
            json!({"log_ref":self.reference,"cursor":self.cursor,"limit":128}),
        )
        .await?;
        if !self.valid() {
            return Err(REFUSED);
        }
        let (batch, cursor) = batch(&value)?;
        self.cursor = cursor;
        Ok(batch)
    }
}

fn batch(value: &Value) -> Result<(LogBatch, Option<String>), &'static str> {
    if value
        .as_object()
        .is_none_or(|v| v.len() != 3 || !v.contains_key("cursor"))
    {
        return Err(REFUSED);
    }
    let rows = value["records"].as_array().ok_or(REFUSED)?;
    let gap = value["gap"].as_bool().ok_or(REFUSED)?;
    let cursor = match &value["cursor"] {
        Value::Null => None,
        Value::String(s) if s.len() <= 1024 => Some(s.clone()),
        _ => return Err(REFUSED),
    };
    if rows.len() > 128 {
        return Err(REFUSED);
    }
    let mut messages = Vec::new();
    for row in rows {
        if row.as_object().is_none_or(|o| o.len() != 1) {
            return Err(REFUSED);
        }
        let text = row["message"].as_str().ok_or(REFUSED)?;
        if text.len() > 16384 {
            return Err(REFUSED);
        }
        messages.push(
            text.chars()
                .filter(|c| !c.is_control() || matches!(c, '\n' | '\t'))
                .collect(),
        );
    }
    Ok((LogBatch { messages, gap }, cursor))
}
