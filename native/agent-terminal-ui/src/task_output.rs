//! Bounded unary reply artifacts, separate from durable terminal-event evidence.
use crate::correlation::TaskState;
use serde_json::Value;

const MAX_TEXT_BYTES: usize = 256 * 1024;
const INVALID: &str = "Invalid or oversized task reply";

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub enum TaskOutput {
    #[default]
    Unavailable,
    Text(String),
}

impl TaskOutput {
    pub(crate) fn from_task(task: &Value, state: TaskState) -> Result<Self, &'static str> {
        if state != TaskState::Completed {
            return Ok(Self::Unavailable);
        }
        let Some(artifacts) = task.get("artifacts").filter(|value| !value.is_null()) else {
            return Ok(Self::Unavailable);
        };
        let artifacts = artifacts
            .as_array()
            .filter(|items| items.len() <= 32)
            .ok_or(INVALID)?;
        if artifacts.is_empty() {
            return Ok(Self::Unavailable);
        }
        let mut output = String::new();
        let mut bytes = 0_usize;
        for (index, artifact) in artifacts.iter().enumerate() {
            let parts = artifact
                .get("parts")
                .and_then(Value::as_array)
                .filter(|parts| !parts.is_empty() && parts.len() <= 32)
                .ok_or(INVALID)?;
            if index > 0 {
                bytes = bytes.checked_add(1).ok_or(INVALID)?;
                if bytes > MAX_TEXT_BYTES {
                    return Err(INVALID);
                }
                output.push('\n');
            }
            for part in parts {
                if part.get("kind").and_then(Value::as_str) != Some("text") {
                    return Err(INVALID);
                }
                let text = part.get("text").and_then(Value::as_str).ok_or(INVALID)?;
                bytes = bytes.checked_add(text.len()).ok_or(INVALID)?;
                if bytes > MAX_TEXT_BYTES {
                    return Err(INVALID);
                }
                output.extend(text.chars().filter(|c| {
                    (!c.is_control() || matches!(c, '\n' | '\t'))
                        && !matches!(c, '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}')
                }));
            }
        }
        Ok(Self::Text(output))
    }

    pub fn text(&self) -> String {
        match self {
            Self::Unavailable => "Reply: unavailable".to_owned(),
            Self::Text(text) if text.is_empty() => "Reply: (empty)".to_owned(),
            Self::Text(text) => format!("Reply:\n{text}"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn completed_parts_preserve_order_unicode_and_literal_text() {
        let task = json!({"artifacts":[
            {"parts":[{"kind":"text","text":"[bold]hello "},{"kind":"text","text":"界\n\t"}]},
            {"parts":[{"kind":"text","text":"second\u{001b}[2J\u{0007}\u{202e}"}]}
        ]});
        assert_eq!(
            TaskOutput::from_task(&task, TaskState::Completed)
                .unwrap()
                .text(),
            "Reply:\n[bold]hello 界\n\t\nsecond[2J"
        );
    }

    #[test]
    fn unavailable_and_empty_are_distinct_and_noncompleted_text_is_not_a_reply() {
        for task in [
            json!({}),
            json!({"artifacts":null}),
            json!({"artifacts":[]}),
        ] {
            assert_eq!(
                TaskOutput::from_task(&task, TaskState::Completed).unwrap(),
                TaskOutput::Unavailable
            );
        }
        let empty = json!({"artifacts":[{"parts":[{"kind":"text","text":""}]}]});
        assert_eq!(
            TaskOutput::from_task(&empty, TaskState::Completed)
                .unwrap()
                .text(),
            "Reply: (empty)"
        );
        for state in [
            TaskState::Working,
            TaskState::Failed,
            TaskState::Canceled,
            TaskState::InputRequired,
        ] {
            assert_eq!(
                TaskOutput::from_task(&empty, state).unwrap(),
                TaskOutput::Unavailable
            );
        }
    }

    #[test]
    fn malformed_or_oversized_output_is_refused_without_a_partial_reply() {
        for artifacts in [
            json!({}),
            json!([{}]),
            json!([{"parts":[]}]),
            json!([{"parts":[{"kind":"file","file":{"bytes":"hidden"}}]}]),
            json!([{"parts":[{"kind":"text","text":42}]}]),
            json!([{"parts":[{"kind":"text","text":"é".repeat(MAX_TEXT_BYTES / 2 + 1)}]}]),
            json!(vec![json!({"parts":[{"kind":"text","text":""}]}); 33]),
            json!([{"parts":vec![json!({"kind":"text","text":""});33]}]),
        ] {
            assert_eq!(
                TaskOutput::from_task(&json!({"artifacts":artifacts}), TaskState::Completed),
                Err(INVALID)
            );
        }
        let exact =
            json!({"artifacts":[{"parts":[{"kind":"text","text":"x".repeat(MAX_TEXT_BYTES)}]}]});
        assert!(matches!(
            TaskOutput::from_task(&exact, TaskState::Completed),
            Ok(TaskOutput::Text(_))
        ));
    }
}
