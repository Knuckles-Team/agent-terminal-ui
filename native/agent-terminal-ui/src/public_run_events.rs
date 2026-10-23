//! The versioned public projection, never opaque producer payloads or thoughts.
use crate::{ArboraClient, run_inspector::ReadRefusal};
use serde_json::{Value, json};
use std::collections::HashSet;

pub const SCHEMA: &str = "arbora-run-events-v1";
pub const MAX_EVENTS: usize = 1000;
pub const MAX_VIEW_BYTES: usize = 131_072;
const MAX_SEQUENCE: u64 = i64::MAX as u64;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PublicEvent {
    pub event_id: String,
    pub sequence: u64,
    pub summary: Option<String>,
    pub text: String,
    pub terminal: bool,
}

#[derive(Debug)]
pub struct PublicPage {
    pub events: Vec<PublicEvent>,
    pub next_after: u64,
    pub has_more: bool,
    pub terminal: bool,
}

pub fn literal(value: &str) -> String {
    value
        .chars()
        .filter(|c| {
            (!c.is_control() || matches!(c, '\n' | '\t'))
                && !matches!(c, '\u{061c}' | '\u{200e}' | '\u{200f}' | '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}')
        })
        .collect()
}

fn identifier(value: &Value, maximum: usize) -> Option<&str> {
    value.as_str().filter(|s| {
        !s.trim().is_empty()
            && s.chars().count() <= maximum
            && !s.chars().any(char::is_control)
            && literal(s) == *s
    })
}

impl PublicEvent {
    fn parse(value: &Value, run_id: &str) -> Result<Self, ReadRefusal> {
        let sequence = value["sequence"]
            .as_u64()
            .filter(|n| *n > 0 && *n <= MAX_SEQUENCE)
            .ok_or(ReadRefusal::Unavailable)?;
        let event_id = identifier(&value["event_id"], 1024).ok_or(ReadRefusal::Unavailable)?;
        let task_id = identifier(&value["task_id"], 512).ok_or(ReadRefusal::Unavailable)?;
        let kind = value["type"].as_str().ok_or(ReadRefusal::Unavailable)?;
        let is_summary = kind == "public_summary";
        let terminal = matches!(kind, "graph_complete" | "error" | "run_cancelled");
        if value["schema_version"].as_str() != Some(SCHEMA)
            || value["run_id"].as_str() != Some(run_id)
            || value["terminal"].as_bool() != Some(terminal)
            || value["category"].as_str()
                != Some(if is_summary {
                    "public_summary"
                } else {
                    "execution_trace"
                })
            || !matches!(
                kind,
                "run_started"
                    | "node_transition"
                    | "graph_complete"
                    | "error"
                    | "run_cancelled"
                    | "task_started"
                    | "task_completed"
                    | "task_failed"
                    | "task_cancelled"
                    | "task_blocked"
                    | "public_summary"
            )
        {
            return Err(ReadRefusal::Unavailable);
        }
        let payload = value["payload"]
            .as_object()
            .ok_or(ReadRefusal::Unavailable)?;
        let summary = if is_summary {
            let summary = payload
                .get("summary")
                .and_then(Value::as_str)
                .filter(|s| !s.is_empty() && s.chars().count() <= 16_384)
                .ok_or(ReadRefusal::Unavailable)?;
            Some(literal(summary))
        } else {
            None
        };
        let text = if let Some(summary) = &summary {
            summary.clone()
        } else {
            let mut fields = vec![format!("{sequence}. {kind} · task {task_id}")];
            for key in ["status", "node", "from_node", "to_node", "error_type"] {
                if let Some(field) = payload.get(key) {
                    let text = field
                        .as_str()
                        .filter(|s| s.chars().count() <= 256)
                        .ok_or(ReadRefusal::Unavailable)?;
                    fields.push(format!("{key}: {}", literal(text)));
                }
            }
            if let Some(field) = payload.get("step") {
                let step = field
                    .as_u64()
                    .filter(|n| *n <= MAX_SEQUENCE)
                    .ok_or(ReadRefusal::Unavailable)?;
                fields.push(format!("step: {step}"));
            }
            if let Some(field) = payload.get("depends_on") {
                let items = field
                    .as_array()
                    .filter(|items| items.len() <= 64)
                    .ok_or(ReadRefusal::Unavailable)?;
                let dependencies: Result<Vec<_>, _> = items
                    .iter()
                    .map(|item| identifier(item, 512).ok_or(ReadRefusal::Unavailable))
                    .collect();
                fields.push(format!("depends_on: {}", dependencies?.join(", ")));
            }
            fields.join("\n")
        };
        Ok(Self {
            event_id: event_id.to_owned(),
            sequence,
            summary,
            text,
            terminal,
        })
    }
}

impl PublicPage {
    pub fn parse(value: &Value, run_id: &str, after: u64) -> Result<Self, ReadRefusal> {
        if after > MAX_SEQUENCE
            || identifier(&json!(run_id), 512).is_none()
            || value["schema_version"].as_str() != Some(SCHEMA)
            || value["run_id"].as_str() != Some(run_id)
            || value["availability"].as_str() != Some("available")
            || value["after"].as_u64() != Some(after)
            || value.to_string().len() > 1_048_576
        {
            return Err(ReadRefusal::Unavailable);
        }
        let raw = value["events"]
            .as_array()
            .filter(|events| events.len() <= MAX_EVENTS)
            .ok_or(ReadRefusal::Unavailable)?;
        let mut events: Vec<PublicEvent> = Vec::new();
        let mut ids = HashSet::new();
        for (index, raw) in raw.iter().enumerate() {
            let event = PublicEvent::parse(raw, run_id)?;
            if Some(event.sequence) != after.checked_add(index as u64 + 1)
                || !ids.insert(event.event_id.clone())
                || events.last().is_some_and(|event| event.terminal)
            {
                return Err(ReadRefusal::Unavailable);
            }
            events.push(event);
        }
        let next_after = events.last().map_or(after, |event| event.sequence);
        let terminal = events.last().is_some_and(|event| event.terminal)
            || (events.is_empty() && after > 0 && value["terminal"].as_bool() == Some(true));
        let has_more = value["has_more"]
            .as_bool()
            .ok_or(ReadRefusal::Unavailable)?;
        if value["next_after"].as_u64() != Some(next_after)
            || value["terminal"].as_bool() != Some(terminal)
            || (has_more && (events.is_empty() || terminal))
        {
            return Err(ReadRefusal::Unavailable);
        }
        Ok(Self {
            events,
            next_after,
            has_more,
            terminal,
        })
    }
}

impl ArboraClient {
    pub async fn get_public_run_events(
        &self,
        run_id: &str,
        task_id: &str,
        after: u64,
    ) -> Result<PublicPage, ReadRefusal> {
        if after > MAX_SEQUENCE || identifier(&json!(task_id), 512).is_none() {
            return Err(ReadRefusal::Unavailable);
        }
        let value = self
            .read_run_operation(
                "runs.events",
                run_id,
                json!({"run_id": run_id, "task_id": task_id, "after": after, "limit": MAX_EVENTS}),
            )
            .await?;
        PublicPage::parse(&value, run_id, after)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> Value {
        serde_json::from_str(include_str!(
            "../../../tests/fixtures/public_run_events.json"
        ))
        .unwrap()
    }

    // spec: TUI-RUNTIME-R008.2.3.2.2.1
    #[test]
    fn shared_fixture_renders_public_summary_separately_and_ignores_private_fields() {
        let mut value = fixture();
        for event in value["events"].as_array_mut().unwrap() {
            event["reasoning"] = json!("private sentinel");
            event["payload"]["thought"] = json!("private sentinel");
        }
        value["events"][1]["payload"]["summary"] =
            json!("[bold]public[/bold]\u{001b}\u{0007}\u{202e}\u{2066}");
        let page = PublicPage::parse(&value, "run-1", 0).unwrap();
        assert_eq!(
            page.events[1].summary.as_deref(),
            Some("[bold]public[/bold]")
        );
        assert!(!format!("{page:?}").contains("private sentinel"));
        assert!(page.terminal);
        assert_eq!(page.next_after, 5);
    }

    // spec: TUI-RUNTIME-R008.2.3.2.2.1
    #[test]
    fn resumed_empty_terminal_page_uses_authoritative_cursor_without_invented_events() {
        let mut value = fixture();
        value["events"] = json!([]);
        value["after"] = json!(5);
        let page = PublicPage::parse(&value, "run-1", 5).unwrap();
        assert!(page.events.is_empty() && page.terminal && !page.has_more);
        assert_eq!(page.next_after, 5);
        value["has_more"] = json!(true);
        assert!(PublicPage::parse(&value, "run-1", 5).is_err());
        value["has_more"] = json!(false);
        value["after"] = json!(0);
        value["next_after"] = json!(0);
        assert!(PublicPage::parse(&value, "run-1", 0).is_err());
    }

    // spec: TUI-RUNTIME-R008.2.3.2.2.1
    #[test]
    fn malformed_identity_order_cursor_category_and_terminal_are_refused() {
        for (pointer, change) in [
            ("/run_id", json!("foreign")),
            ("/schema_version", json!("unknown")),
            ("/after", json!(true)),
            ("/next_after", json!(6)),
            ("/terminal", json!(false)),
            ("/has_more", json!(true)),
            ("/events/0/run_id", json!("foreign")),
            ("/events/0/sequence", json!(true)),
            ("/events/0/sequence", json!(2)),
            ("/events/0/type", json!("reasoning")),
            ("/events/0/category", json!("public_summary")),
            ("/events/1/event_id", json!("public-event-1")),
            ("/events/1/payload/summary", json!("x".repeat(16_385))),
        ] {
            let mut value = fixture();
            *value.pointer_mut(pointer).unwrap() = change;
            assert!(PublicPage::parse(&value, "run-1", 0).is_err(), "{pointer}");
        }
    }
}
