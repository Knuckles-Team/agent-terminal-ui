//! Caller-authenticated GraphOS run reads; no local run authority or counters.
use crate::run_inspector::{
    AppliedConfig, PlanItem, PlanRefusal, PlanSnapshot, PlanStatus, PlanValidator, ReadRefusal,
    RunInspector, RunProjection,
};
use crate::{GraphOsClient, read_task_response};
use serde_json::Value;
use std::time::{Duration, Instant};
use time::{OffsetDateTime, UtcOffset, format_description::well_known::Rfc3339};

pub struct RunRead {
    projection: RunProjection,
    validity: Option<SnapshotValidity>,
}

impl RunRead {
    pub fn apply(self, inspector: &mut RunInspector, now: Instant) -> Result<(), ReadRefusal> {
        inspector.accept(
            Ok(self.projection),
            self.validity.as_ref().map(|v| v as &dyn PlanValidator),
            now,
        )
    }
}

impl RunInspector {
    /// Clear protected values on every failed transport read.
    pub fn accept_read(
        &mut self,
        result: Result<RunRead, ReadRefusal>,
        now: Instant,
    ) -> Result<(), ReadRefusal> {
        match result {
            Ok(read) => read.apply(self, now),
            Err(error) => self.accept(Err(error), None, now),
        }
    }
}

struct SnapshotValidity {
    run_id: String,
    revision: u64,
    observed_at: String,
    deadline: Instant,
}

impl PlanValidator for SnapshotValidity {
    fn validate(
        &self,
        plan: &PlanSnapshot,
        previous: Option<&str>,
        now: Instant,
    ) -> Result<Instant, PlanRefusal> {
        if plan.run_id != self.run_id
            || plan.revision != self.revision.to_string()
            || plan.observed_at != self.observed_at
        {
            return Err(PlanRefusal::Malformed);
        }
        if let Some(previous) = previous {
            let previous = previous
                .parse::<u64>()
                .map_err(|_| PlanRefusal::Malformed)?;
            if self.revision < previous {
                return Err(PlanRefusal::Regressing);
            }
        }
        if self.deadline <= now {
            return Err(PlanRefusal::Expired);
        }
        Ok(self.deadline)
    }
}

impl GraphOsClient {
    /// Read only after this caller's registry advertises the operation.
    pub async fn get_run(&self, run_id: &str) -> Result<RunRead, ReadRefusal> {
        if !self.authenticated {
            return Err(ReadRefusal::Denied);
        }
        if run_id.is_empty() || run_id.chars().count() > 512 || run_id.chars().any(char::is_control)
        {
            return Err(ReadRefusal::Unavailable);
        }
        let mut url = self.card_url.clone();
        url.set_path("/api/v1/registry");
        let registry = response_json(self.http.get(url.clone()).send().await).await?;
        let digest = registry
            .get("registry_digest")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
            .ok_or(ReadRefusal::Unavailable)?;
        if registry.get("api_version").and_then(Value::as_str) != Some("v1")
            || !registry
                .get("ops")
                .and_then(Value::as_array)
                .is_some_and(|ops| {
                    ops.iter()
                        .any(|op| op.get("id").and_then(Value::as_str) == Some("runs.get"))
                })
        {
            return Err(ReadRefusal::Unavailable);
        }
        url.set_path("/api/v1/ops/runs.get");
        let body = response_json(
            self.http
                .post(url)
                .json(&serde_json::json!({"run_id": run_id}))
                .send()
                .await,
        )
        .await?;
        if body
            .pointer("/meta/registry_digest")
            .and_then(Value::as_str)
            != Some(digest)
            || body.pointer("/meta/api_version").and_then(Value::as_str) != Some("v1")
            || body.get("ok").and_then(Value::as_bool) != Some(true)
        {
            return Err(ReadRefusal::Unavailable);
        }
        decode_run(
            body.pointer("/result/value")
                .ok_or(ReadRefusal::Unavailable)?,
            run_id,
            OffsetDateTime::now_utc(),
            Instant::now(),
        )
    }
}

async fn response_json(
    response: Result<reqwest::Response, reqwest::Error>,
) -> Result<Value, ReadRefusal> {
    let response = response.map_err(|error| {
        if error.is_timeout() {
            ReadRefusal::Timeout
        } else {
            ReadRefusal::Unavailable
        }
    })?;
    if matches!(response.status().as_u16(), 401 | 403) {
        return Err(ReadRefusal::Denied);
    }
    if !response.status().is_success() {
        return Err(ReadRefusal::Unavailable);
    }
    let bytes = read_task_response(response)
        .await
        .map_err(|_| ReadRefusal::Unavailable)?;
    serde_json::from_slice(&bytes).map_err(|_| ReadRefusal::Unavailable)
}

fn optional<T>(
    value: &Value,
    name: &str,
    parse: impl FnOnce(&Value) -> Option<T>,
) -> Result<Option<T>, ReadRefusal> {
    match value.get(name) {
        None | Some(Value::Null) => Ok(None),
        Some(field) => parse(field).map(Some).ok_or(ReadRefusal::Unavailable),
    }
}

fn text(value: &Value) -> Option<String> {
    value.as_str().filter(|s| !s.is_empty()).map(str::to_owned)
}

fn config_text(value: &Value) -> Option<String> {
    if value.is_string() {
        text(value)
    } else {
        serde_json::to_string(value).ok()
    }
}

fn decode_run(
    value: &Value,
    run_id: &str,
    wall: OffsetDateTime,
    now: Instant,
) -> Result<RunRead, ReadRefusal> {
    if value.get("run_id").and_then(Value::as_str) != Some(run_id) {
        return Err(ReadRefusal::WrongRun);
    }
    let config_ref = optional(value, "harness_config_ref", text)?;
    let mut config = AppliedConfig {
        reference: config_ref,
        ..AppliedConfig::default()
    };
    if let Some(raw) = value.get("harness_config").filter(|v| !v.is_null()) {
        if !raw.is_object() || config.reference.is_none() {
            return Err(ReadRefusal::Unavailable);
        }
        config.context_policy = optional(raw, "context_policy", config_text)?;
        config.plan_scaffold = optional(raw, "plan_scaffold", config_text)?;
        config.action_space = optional(raw, "action_space", config_text)?;
    }
    let (current_plan, validity) =
        decode_plan(value.get("current_plan"), run_id, wall, now).unwrap_or((None, None));
    Ok(RunRead {
        projection: RunProjection {
            run_id: run_id.to_owned(),
            peak_context_tokens: optional(value, "peak_context_tokens", Value::as_u64)?,
            context_budget_tokens: optional(value, "context_budget_tokens", Value::as_u64)?,
            cost_usd: optional(value, "cost_usd", |v| {
                v.as_f64().filter(|n| n.is_finite() && *n >= 0.0)
            })?,
            termination_reason: optional(value, "termination_reason", text)?,
            config,
            current_plan,
        },
        validity,
    })
}

fn decode_plan(
    value: Option<&Value>,
    run_id: &str,
    wall: OffsetDateTime,
    now: Instant,
) -> Option<(Option<PlanSnapshot>, Option<SnapshotValidity>)> {
    let value = value?;
    if value.get("availability")?.as_str()? != "available" {
        return None;
    }
    let plan = value.get("snapshot")?;
    if plan.get("run_id")?.as_str()? != run_id {
        return None;
    }
    let revision = plan.get("revision")?.as_u64()?;
    let observed_at = plan.get("observed_at")?.as_str()?;
    let observed = OffsetDateTime::parse(observed_at, &Rfc3339).ok()?;
    let expires = OffsetDateTime::parse(plan.get("expires_at")?.as_str()?, &Rfc3339).ok()?;
    if observed.offset() != UtcOffset::UTC
        || expires.offset() != UtcOffset::UTC
        || observed > wall
        || expires <= wall
        || expires <= observed
    {
        return None;
    }
    let remaining = Duration::try_from(expires - wall).ok()?;
    let deadline = now.checked_add(remaining)?;
    let items: Option<Vec<_>> = plan
        .get("items")?
        .as_array()?
        .iter()
        .map(|item| {
            Some(PlanItem {
                text: text(item.get("text")?)?,
                status: match item.get("status")?.as_str()? {
                    "pending" => PlanStatus::Pending,
                    "in_progress" => PlanStatus::InProgress,
                    "done" => PlanStatus::Done,
                    _ => return None,
                },
            })
        })
        .collect();
    Some((
        Some(PlanSnapshot {
            run_id: run_id.to_owned(),
            revision: revision.to_string(),
            observed_at: observed_at.to_owned(),
            items: items?,
        }),
        Some(SnapshotValidity {
            run_id: run_id.to_owned(),
            revision,
            observed_at: observed_at.to_owned(),
            deadline,
        }),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn payload(revision: u64) -> Value {
        json!({"run_id":"r", "peak_context_tokens":0, "cost_usd":0.0,
            "current_plan":{"availability":"available", "snapshot":{
                "run_id":"r", "revision":revision,
                "observed_at":"2026-10-17T00:00:00Z", "expires_at":"2026-10-17T00:00:30Z",
                "items":[{"text":"private plan", "status":"pending"}]}}})
    }

    fn wall() -> OffsetDateTime {
        OffsetDateTime::parse("2026-10-17T00:00:01Z", &Rfc3339).unwrap()
    }

    // spec: TUI-RUNTIME-R010.8
    #[test]
    fn wire_zero_expiry_regression_and_refusal_preserve_boundaries() {
        let now = Instant::now();
        let mut inspector = RunInspector::new("r".into());
        decode_run(&payload(2), "r", wall(), now)
            .unwrap()
            .apply(&mut inspector, now)
            .unwrap();
        let rendered = inspector.text(now);
        assert!(rendered.contains("Peak context tokens: 0"));
        assert!(rendered.contains("Context budget tokens: unavailable"));
        assert!(rendered.contains("private plan"));
        decode_run(&payload(1), "r", wall(), now)
            .unwrap()
            .apply(&mut inspector, now)
            .unwrap();
        assert!(!inspector.text(now).contains("private plan"));
        decode_run(&payload(2), "r", wall(), now)
            .unwrap()
            .apply(&mut inspector, now)
            .unwrap();
        assert!(
            !inspector
                .text(now + Duration::from_secs(30))
                .contains("private plan")
        );
        decode_run(&payload(3), "r", wall(), now)
            .unwrap()
            .apply(&mut inspector, now)
            .unwrap();
        assert_eq!(
            inspector.accept(Err(ReadRefusal::Denied), None, now),
            Err(ReadRefusal::Denied)
        );
        assert!(!inspector.text(now).contains("private plan"));
    }

    // spec: TUI-RUNTIME-R010.8
    #[test]
    fn malformed_and_foreign_snapshots_never_render() {
        let now = Instant::now();
        for (field, bad) in [
            ("run_id", json!("other")),
            ("revision", json!(-1)),
            ("revision", json!("3")),
            ("observed_at", json!("2026-10-17T01:00:00Z")),
            ("expires_at", json!("2026-10-17T00:00:00Z")),
            (
                "items",
                json!([{"text":"private plan", "status":"invented"}]),
            ),
        ] {
            let mut value = payload(3);
            value["current_plan"]["snapshot"][field] = bad;
            let mut inspector = RunInspector::new("r".into());
            decode_run(&value, "r", wall(), now)
                .unwrap()
                .apply(&mut inspector, now)
                .unwrap();
            assert!(!inspector.text(now).contains("private plan"));
        }
        assert!(matches!(
            decode_run(&payload(3), "other", wall(), now),
            Err(ReadRefusal::WrongRun)
        ));
        let mut value = payload(3);
        value["peak_context_tokens"] = json!("0");
        assert!(decode_run(&value, "r", wall(), now).is_err());
    }

    // spec: TUI-RUNTIME-R010.8
    #[test]
    fn available_empty_is_distinct_from_unavailable() {
        let now = Instant::now();
        let mut value = payload(0);
        value["current_plan"]["snapshot"]["items"] = json!([]);
        let mut inspector = RunInspector::new("r".into());
        decode_run(&value, "r", wall(), now)
            .unwrap()
            .apply(&mut inspector, now)
            .unwrap();
        assert!(inspector.text(now).contains("available (empty)"));
        value["current_plan"] = json!({"availability":"unavailable", "snapshot":null});
        decode_run(&value, "r", wall(), now)
            .unwrap()
            .apply(&mut inspector, now)
            .unwrap();
        assert!(inspector.text(now).contains("Current plan: unavailable"));
    }
}

#[cfg(test)]
mod transport_tests {
    use super::*;
    use tokio::{
        io::{AsyncReadExt, AsyncWriteExt},
        net::TcpListener,
    };

    async fn server(
        responses: Vec<(u16, Value)>,
    ) -> (String, tokio::task::JoinHandle<Vec<String>>) {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let handle = tokio::spawn(async move {
            let mut requests = Vec::new();
            for (status, body) in responses {
                let (mut socket, _) = listener.accept().await.unwrap();
                let mut bytes = Vec::new();
                loop {
                    let mut buffer = [0; 4096];
                    let count = socket.read(&mut buffer).await.unwrap();
                    assert!(count > 0);
                    bytes.extend_from_slice(&buffer[..count]);
                    let request = String::from_utf8_lossy(&bytes);
                    if let Some((head, body)) = request.split_once("\r\n\r\n") {
                        let length: usize = head
                            .lines()
                            .find_map(|line| {
                                let (key, value) = line.split_once(':')?;
                                key.eq_ignore_ascii_case("content-length")
                                    .then(|| value.trim().parse().unwrap())
                            })
                            .unwrap_or(0);
                        if body.len() >= length {
                            break;
                        }
                    }
                }
                requests.push(String::from_utf8(bytes).unwrap());
                let body = body.to_string();
                let response = format!(
                    "HTTP/1.1 {status} Test\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                );
                socket.write_all(response.as_bytes()).await.unwrap();
            }
            assert!(
                tokio::time::timeout(Duration::from_millis(30), listener.accept())
                    .await
                    .is_err()
            );
            requests
        });
        (endpoint, handle)
    }

    fn registry(ops: Value) -> Value {
        serde_json::json!({"api_version":"v1", "registry_digest":"d", "ops":ops})
    }

    // spec: TUI-RUNTIME-R010.8
    #[tokio::test]
    async fn advertised_read_uses_credentials_exact_run_and_digest() {
        let body = serde_json::json!({"ok":true,"meta":{"api_version":"v1","registry_digest":"d"},"result":{"value":{"run_id":"r","peak_context_tokens":0,"current_plan":{"availability":"unavailable","snapshot":null}}}});
        let (endpoint, server) = server(vec![
            (200, registry(serde_json::json!([{"id":"runs.get"}]))),
            (200, body),
        ])
        .await;
        let client = GraphOsClient::new(&endpoint, Some("fixture-credential")).unwrap();
        let mut inspector = RunInspector::new("r".into());
        inspector
            .accept_read(client.get_run("r").await, Instant::now())
            .unwrap();
        assert!(
            inspector
                .text(Instant::now())
                .contains("Peak context tokens: 0")
        );
        let requests = server.await.unwrap();
        assert!(requests[0].starts_with("GET /api/v1/registry "));
        assert!(requests[1].starts_with("POST /api/v1/ops/runs.get "));
        assert!(requests.iter().all(|r| {
            r.to_lowercase()
                .contains("authorization: bearer fixture-credential")
        }));
        assert!(requests[1].ends_with("{\"run_id\":\"r\"}"));
    }

    // spec: TUI-RUNTIME-R010.8
    #[tokio::test]
    async fn absent_operation_does_not_dispatch_and_changed_digest_refuses() {
        let (endpoint, task) = server(vec![(200, registry(serde_json::json!([])))]).await;
        let client = GraphOsClient::new(&endpoint, Some("fixture-credential")).unwrap();
        assert!(matches!(
            client.get_run("r").await,
            Err(ReadRefusal::Unavailable)
        ));
        assert_eq!(task.await.unwrap().len(), 1);
        let body = serde_json::json!({"ok":true,"meta":{"api_version":"v1","registry_digest":"other"},"result":{"value":{"run_id":"r","peak_context_tokens":44}}});
        let (endpoint, task) = server(vec![
            (200, registry(serde_json::json!([{"id":"runs.get"}]))),
            (200, body),
        ])
        .await;
        let client = GraphOsClient::new(&endpoint, Some("fixture-credential")).unwrap();
        assert!(matches!(
            client.get_run("r").await,
            Err(ReadRefusal::Unavailable)
        ));
        task.await.unwrap();
    }
}
