//! Authenticated, read-only host log transport. Bindings cannot be constructed by callers.
use crate::ArboraClient;
use serde_json::{Value, json};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub const REFUSED: &str = "Host logs unavailable. Authenticated host access is required.";

pub const RETENTION_GAP: &str =
    "Host log history gap: the resume position is no longer retained. Fresh admission is required.";

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct HostLaunchReceipt {
    version: u64,
    pub log_ref: String,
    host_instance: String,
    workspace: String,
    tenant: String,
    principal: String,
    session_ref: String,
    policy_revision: String,
    grant_revision: String,
    expires_at_ms: u64,
    interface_mode: String,
    web_logs: bool,
    ready: bool,
}

impl HostLaunchReceipt {
    pub fn parse(value: &Value) -> Result<Self, &'static str> {
        let object = value.as_object().ok_or(REFUSED)?;
        let text = |key: &str, max: usize| -> Result<String, &'static str> {
            let value = value[key].as_str().ok_or(REFUSED)?;
            if value.is_empty() || value.len() > max || value.chars().any(char::is_control) {
                return Err(REFUSED);
            }
            Ok(value.to_owned())
        };
        if object.len() != 13
            || value["version"].as_u64() != Some(1)
            || value["ready"].as_bool() != Some(true)
            || value["web_logs"].as_bool() != Some(true)
            || !matches!(value["interface_mode"].as_str(), Some("terminal" | "both"))
        {
            return Err(REFUSED);
        }
        let receipt = Self {
            version: 1,
            log_ref: text("log_ref", 128)?,
            host_instance: text("host_instance", 4096)?,
            workspace: text("workspace", 4096)?,
            tenant: text("tenant", 4096)?,
            principal: text("principal", 4096)?,
            session_ref: text("session_ref", 4096)?,
            policy_revision: text("policy_revision", 4096)?,
            grant_revision: text("grant_revision", 4096)?,
            expires_at_ms: value["expires_at_ms"].as_u64().ok_or(REFUSED)?,
            interface_mode: value["interface_mode"].as_str().unwrap().to_owned(),
            web_logs: true,
            ready: true,
        };
        if receipt.expires_at_ms <= now_ms() {
            return Err(REFUSED);
        }
        Ok(receipt)
    }

    pub fn expires_at_ms(&self) -> u64 {
        self.expires_at_ms
    }
}

pub struct HostLogReader {
    logs: HostLogs,
}

impl HostLogReader {
    fn from_logs(logs: HostLogs) -> Self {
        Self { logs }
    }

    fn receipt(&self) -> &HostLaunchReceipt {
        &self.logs.receipt
    }

    pub async fn read(
        &mut self,
        log_ref: &str,
        cursor: Option<&str>,
        limit: usize,
    ) -> Result<LogBatch, &'static str> {
        if log_ref != self.receipt().log_ref || cursor != self.logs.cursor.as_deref() {
            return Err(REFUSED);
        }
        self.logs.read_with_limit(limit).await
    }

    pub async fn read_next(&mut self) -> Result<LogBatch, &'static str> {
        let log_ref = self.receipt().log_ref.clone();
        let cursor = self.logs.cursor.clone();
        self.read(&log_ref, cursor.as_deref(), 128).await
    }

    pub fn valid(&self) -> bool {
        self.logs.valid()
    }

    pub fn expires_at_ms(&self) -> u64 {
        self.logs.expires_at_ms()
    }
}

pub fn run_host_terminal(
    receipt: HostLaunchReceipt,
    client: std::sync::Arc<ArboraClient>,
    log_reader: Option<HostLogReader>,
) -> Result<HostLogReader, &'static str> {
    if !client.authenticated {
        return Err(REFUSED);
    }
    let reader = log_reader.ok_or(REFUSED)?;
    if !std::sync::Arc::ptr_eq(&reader.logs.client, &client) || reader.receipt() != &receipt {
        return Err(REFUSED);
    }
    Ok(reader)
}

pub struct HostLogs {
    reference: String,
    expires: u64,
    cursor: Option<String>,
    client: std::sync::Arc<ArboraClient>,
    receipt: HostLaunchReceipt,
}

pub struct LogBatch {
    pub records: Vec<LogRecord>,
    pub gap: bool,
}

#[derive(Debug)]
pub struct LogRecord {
    pub host_instance: String,
    pub sequence: u64,
    pub request: String,
    pub timestamp: f64,
    pub severity: String,
    pub message: String,
}

impl LogRecord {
    pub fn display(&self) -> String {
        format!(
            "[{} {} host={} seq={} request={}] {}",
            self.timestamp,
            self.severity,
            self.host_instance,
            self.sequence,
            self.request,
            self.message
        )
    }
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

async fn post(client: &ArboraClient, path: &str, body: Value) -> Result<Value, &'static str> {
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
        let status = response.status();
        let mut bytes = Vec::new();
        while let Some(chunk) = response.chunk().await.map_err(|_| REFUSED)? {
            if bytes.len() + chunk.len() > 2 * 1024 * 1024 {
                return Err(REFUSED);
            }
            bytes.extend_from_slice(&chunk);
        }
        let value: Value = serde_json::from_slice(&bytes).map_err(|_| REFUSED)?;
        if status.as_u16() == 409 && value == json!({"detail":"retention_gap"}) {
            return Err(RETENTION_GAP);
        }
        if !status.is_success() {
            return Err(REFUSED);
        }
        Ok(value)
    })
    .await
    .map_err(|_| REFUSED)?
}

impl HostLogs {
    pub async fn bind(client: std::sync::Arc<ArboraClient>) -> Result<Self, &'static str> {
        let value = post(&client, "/host/logs/reference", json!({})).await?;
        let receipt = HostLaunchReceipt::parse(&value)?;
        Ok(Self {
            reference: receipt.log_ref.clone(),
            expires: receipt.expires_at_ms(),
            cursor: None,
            client,
            receipt,
        })
    }

    pub fn receipt(&self) -> &HostLaunchReceipt {
        &self.receipt
    }

    pub fn into_reader(self) -> HostLogReader {
        HostLogReader::from_logs(self)
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
        self.read_with_limit(128).await
    }

    async fn read_with_limit(&mut self, limit: usize) -> Result<LogBatch, &'static str> {
        if !(1..=128).contains(&limit) {
            return Err(REFUSED);
        }
        let result = self.read_inner(limit).await;
        if result.is_err() {
            self.expires = 0;
            self.cursor = None;
        }
        result
    }

    async fn read_inner(&mut self, limit: usize) -> Result<LogBatch, &'static str> {
        if !self.valid() {
            return Err(REFUSED);
        }
        let value = post(
            &self.client,
            "/host/logs/read",
            json!({"version":2,"log_ref":self.reference,"cursor":self.cursor,"limit":limit}),
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
        .is_none_or(|v| v.len() != 4 || !v.contains_key("cursor"))
    {
        return Err(REFUSED);
    }
    if value["version"].as_u64() != Some(2) {
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
    let mut records = Vec::new();
    for row in rows {
        if row.as_object().is_none_or(|o| o.len() != 6) {
            return Err(REFUSED);
        }
        let text = |key: &str, max: usize, multiline: bool| -> Result<String, &'static str> {
            let value = row[key].as_str().ok_or(REFUSED)?;
            if value.len() > max {
                return Err(REFUSED);
            }
            Ok(value
                .chars()
                .filter(|c| !c.is_control() || (multiline && matches!(c, '\n' | '\t')))
                .collect())
        };
        let host_instance = text("host_instance", 128, false)?;
        let severity = text("severity", 32, false)?;
        let sequence = row["sequence"]
            .as_u64()
            .filter(|n| *n > 0 && *n <= i64::MAX as u64)
            .ok_or(REFUSED)?;
        let timestamp = row["timestamp"]
            .as_f64()
            .filter(|n| n.is_finite() && *n >= 0.0)
            .ok_or(REFUSED)?;
        if host_instance.is_empty() || severity.is_empty() {
            return Err(REFUSED);
        }
        records.push(LogRecord {
            host_instance,
            sequence,
            request: text("request", 1024, false)?,
            timestamp,
            severity,
            message: text("message", 16384, true)?,
        });
    }
    Ok((LogBatch { records, gap }, cursor))
}
