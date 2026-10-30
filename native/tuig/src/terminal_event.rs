//! Read-only committed terminal identity; never a resume position or authority.
use crate::correlation::{TaskCorrelation, TaskState};
use serde_json::{Map, Value};

const INVALID: &str = "Invalid committed terminal event";

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub enum TerminalEvent {
    LegacyUnavailable,
    #[default]
    ProducerUnavailable,
    Available(Box<CommittedTerminalEvent>),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommittedTerminalEvent {
    tenant: String,
    scope_tenant: String,
    kind: String,
    graph: String,
    incarnation: String,
    scope_digest: [u8; 32],
    batch: String,
    sequence: u64,
    ordinal: u32,
    run: String,
    outcome: String,
    result_ref: Option<String>,
    payload_digest: String,
}

fn object<'a>(value: &'a Value, keys: &[&str]) -> Result<&'a Map<String, Value>, &'static str> {
    let object = value.as_object().ok_or(INVALID)?;
    if object.len() != keys.len() || keys.iter().any(|key| !object.contains_key(*key)) {
        return Err(INVALID);
    }
    Ok(object)
}

fn text(object: &Map<String, Value>, key: &str, limit: usize) -> Result<String, &'static str> {
    let text = object.get(key).and_then(Value::as_str).ok_or(INVALID)?;
    if text.trim().is_empty() || text.len() > limit || text.chars().any(char::is_control) {
        return Err(INVALID);
    }
    Ok(text.to_owned())
}

fn digest(object: &Map<String, Value>, key: &str) -> Result<String, &'static str> {
    let digest = text(object, key, 64)?;
    if digest.len() != 64
        || !digest
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    {
        return Err(INVALID);
    }
    Ok(digest)
}

fn scope_digest(value: &Value) -> Result<[u8; 32], &'static str> {
    let array = value
        .as_array()
        .filter(|array| array.len() == 32)
        .ok_or(INVALID)?;
    let mut digest = [0; 32];
    for (target, value) in digest.iter_mut().zip(array) {
        *target = value
            .as_u64()
            .and_then(|byte| u8::try_from(byte).ok())
            .ok_or(INVALID)?;
    }
    Ok(digest)
}

impl TerminalEvent {
    pub fn from_task(
        task: &Value,
        binding: &TaskCorrelation,
        state: TaskState,
    ) -> Result<Self, &'static str> {
        let Some(value) = task.pointer("/metadata/arbora/terminalEvent") else {
            return Ok(Self::ProducerUnavailable);
        };
        if value.to_string().len() > 16_384 {
            return Err(INVALID);
        }
        match value.get("status").and_then(Value::as_str) {
            Some("unavailable") => {
                let object = object(value, &["status", "reason"])?;
                match object["reason"].as_str() {
                    Some("legacy_unbound") => Ok(Self::LegacyUnavailable),
                    Some("producer_unavailable") => Ok(Self::ProducerUnavailable),
                    _ => Err(INVALID),
                }
            }
            Some("available") => {
                let event = CommittedTerminalEvent::parse(value)?;
                let expected = match event.outcome.as_str() {
                    "succeeded" => TaskState::Completed,
                    "cancelled" => TaskState::Canceled,
                    _ => TaskState::Failed,
                };
                if state != expected {
                    return Err(INVALID);
                }
                let result = Self::Available(Box::new(event));
                result.validate_binding(binding)?;
                Ok(result)
            }
            _ => Err(INVALID),
        }
    }

    pub fn validate_binding(&self, binding: &TaskCorrelation) -> Result<(), &'static str> {
        if let Self::Available(event) = self
            && binding.run_id() != Some(event.run.as_str())
        {
            return Err("Committed terminal event run mismatch");
        }
        Ok(())
    }

    pub fn text(&self) -> String {
        match self {
            Self::LegacyUnavailable => {
                "Committed terminal point-read: unavailable (legacy unbound)".into()
            }
            Self::ProducerUnavailable => {
                "Committed terminal point-read: unavailable (producer unavailable)".into()
            }
            Self::Available(event) => format!(
                "Committed terminal point-read:\nCaller tenant: {}\nPhysical scope tenant: {}\nGraph: {}\nIncarnation: {}\nScope digest (hex of bytes): {}\nBatch: {}\nCommit sequence: {}\nOrdinal: {}\nEvent run: {}\nKind: {}\nOutcome: {}\nResult reference: {}\nPayload digest: {}",
                event.tenant,
                event.scope_tenant,
                event.graph,
                event.incarnation,
                event
                    .scope_digest
                    .iter()
                    .map(|byte| format!("{byte:02x}"))
                    .collect::<String>(),
                event.batch,
                event.sequence,
                event.ordinal,
                event.run,
                event.kind,
                event.outcome,
                event.result_ref.as_deref().unwrap_or("unavailable"),
                event.payload_digest,
            ),
        }
    }
}

impl CommittedTerminalEvent {
    fn parse(value: &Value) -> Result<Self, &'static str> {
        let event = object(
            value,
            &[
                "status",
                "tenant",
                "scope",
                "batch_id",
                "commit_sequence",
                "ordinal",
                "run_id",
                "kind",
                "outcome",
                "result_ref",
                "payload_digest",
            ],
        )?;
        let scope = object(
            &event["scope"],
            &["tenant", "scope", "incarnation_id", "identity_digest"],
        )?;
        let graph = object(&scope["scope"], &["kind", "graph"])?;
        let tenant = text(event, "tenant", 512)?;
        let kind = text(event, "kind", 32)?;
        if graph["kind"] != "graph"
            || !matches!(
                kind.as_str(),
                "outcome" | "tool_call" | "degraded" | "reconciled"
            )
        {
            return Err(INVALID);
        }
        let outcome = text(event, "outcome", 32)?;
        if !matches!(outcome.as_str(), "succeeded" | "failed" | "cancelled") {
            return Err(INVALID);
        }
        let sequence = event["commit_sequence"]
            .as_u64()
            .filter(|n| *n > 0)
            .ok_or(INVALID)?;
        let ordinal = event["ordinal"]
            .as_u64()
            .and_then(|n| u32::try_from(n).ok())
            .ok_or(INVALID)?;
        let result_ref = if event["result_ref"].is_null() {
            None
        } else {
            Some(text(event, "result_ref", 4096)?)
        };
        Ok(Self {
            tenant,
            scope_tenant: text(scope, "tenant", 512)?,
            kind,
            graph: text(graph, "graph", 512)?,
            incarnation: text(scope, "incarnation_id", 512)?,
            scope_digest: scope_digest(&scope["identity_digest"])?,
            batch: text(event, "batch_id", 512)?,
            sequence,
            ordinal,
            run: text(event, "run_id", 512)?,
            outcome,
            result_ref,
            payload_digest: digest(event, "payload_digest")?,
        })
    }
}
