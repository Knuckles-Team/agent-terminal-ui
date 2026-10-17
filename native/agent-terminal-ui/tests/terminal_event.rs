use agent_terminal_ui_native::{
    correlation::{TaskCorrelation, TaskState},
    terminal_event::TerminalEvent,
};
use serde_json::{Value, json};

fn task() -> Value {
    json!({"kind":"task","id":"task-one","contextId":"context-two", "status":{"state":"completed"},
    "metadata":{"graphOs":{"runId":"run-three","terminalEvent":{
        "status":"available","tenant":"tenant-one",
        "scope":{"tenant":"tenant-one","scope":{"kind":"graph","graph":"graph-one"},"incarnation_id":"incarnation-one","identity_digest":vec![170;32]},
        "batch_id":"batch-one","commit_sequence":42,"ordinal":0,"run_id":"run-three", "kind":"outcome","outcome":"succeeded","result_ref":null,"payload_digest":"b".repeat(64)
    }}}})
}
fn decode(task: &Value, state: TaskState) -> Result<TerminalEvent, &'static str> {
    TerminalEvent::from_task(task, &TaskCorrelation::from_task(task)?, state)
}

// spec: TUI-RUNTIME-R002.1.3.2.2.3
#[test]
fn actual_identity_and_outcome_are_preserved_without_cursor() {
    for (outcome, state) in [
        ("succeeded", TaskState::Completed),
        ("failed", TaskState::Failed),
        ("cancelled", TaskState::Canceled),
    ] {
        let mut task = task();
        task["metadata"]["graphOs"]["terminalEvent"]["outcome"] = json!(outcome);
        let event = decode(&task, state).unwrap();
        let text = event.text();
        for expected in [
            "batch-one",
            "Commit sequence: 42",
            "Ordinal: 0",
            "incarnation-one",
            "graph-one",
            outcome,
            &"a".repeat(64),
            &"b".repeat(64),
        ] {
            assert!(text.contains(expected));
        }
        assert!(!text.contains("cursor"));
        assert!(decode(&task, TaskState::Working).is_err());
    }
}

// spec: TUI-RUNTIME-R002.1.3.2.2.3
#[test]
fn omission_and_known_refusals_do_not_disclose_identity() {
    let mut task = task();
    task["metadata"]["graphOs"]
        .as_object_mut()
        .unwrap()
        .remove("terminalEvent");
    assert_eq!(
        decode(&task, TaskState::Completed).unwrap(),
        TerminalEvent::ProducerUnavailable
    );
    for reason in ["legacy_unbound", "producer_unavailable"] {
        task["metadata"]["graphOs"]["terminalEvent"] =
            json!({"status":"unavailable","reason":reason});
        let text = decode(&task, TaskState::Completed).unwrap().text();
        assert!(text.contains("unavailable"));
        assert!(!text.contains("batch-one"));
    }
}

// spec: TUI-RUNTIME-R002.1.3.2.2.3
#[test]
fn malformed_unsafe_and_unbound_events_are_refused() {
    for (path, value) in [
        ("/status", json!("unknown")),
        ("/kind", json!("progress")),
        ("/run_id", json!("foreign")),
        ("/batch_id", json!("bad\nidentity")),
        ("/batch_id", json!("x".repeat(513))),
        ("/commit_sequence", json!(0)),
        ("/commit_sequence", json!(1.5)),
        ("/commit_sequence", json!(-1)),
        ("/ordinal", json!(4294967296u64)),
        ("/payload_digest", json!("z".repeat(64))),
        ("/payload_digest", json!("A".repeat(64))),
        ("/result_ref", json!({})),
        ("/outcome", json!("cancelled")),
        ("/outcome", json!("dead_letter")),
        ("/result_ref", json!("x".repeat(4097))),
        ("/scope/tenant", json!("bad\ntenant")),
        ("/scope/scope/kind", json!("global")),
        ("/scope/identity_digest", json!("short")),
    ] {
        let mut task = task();
        *task["metadata"]["graphOs"]["terminalEvent"]
            .pointer_mut(path)
            .unwrap() = value;
        assert!(decode(&task, TaskState::Completed).is_err(), "{path}");
    }
    for key in ["runId", "terminalEvent"] {
        let mut task = task();
        task["metadata"]["graphOs"][key] = Value::Null;
        assert!(decode(&task, TaskState::Completed).is_err());
    }
    let mut task = task();
    task["metadata"]["graphOs"]["terminalEvent"]["cursor"] = json!("invented");
    assert!(decode(&task, TaskState::Completed).is_err());
    task["metadata"]["graphOs"]["terminalEvent"]["cursor"] = json!("x".repeat(16385));
    assert!(decode(&task, TaskState::Completed).is_err());
}

// spec: TUI-RUNTIME-R002.1.3.2.2.3
#[test]
fn retained_binding_cannot_acquire_or_switch_run() {
    let event = decode(&task(), TaskState::Completed).unwrap();
    for run in [None, Some("other-run")] {
        let mut retained = task();
        retained["metadata"]["graphOs"]
            .as_object_mut()
            .unwrap()
            .remove("runId");
        if let Some(run) = run {
            retained["metadata"]["graphOs"]["runId"] = json!(run);
        }
        assert!(
            event
                .validate_binding(&TaskCorrelation::from_task(&retained).unwrap())
                .is_err()
        );
    }
}

// spec: TUI-RUNTIME-R002.1.3.2.2.3
#[test]
fn physical_scope_tenant_and_actual_producer_kind_are_preserved() {
    for kind in ["outcome", "tool_call", "degraded", "reconciled"] {
        let mut task = task();
        let event = &mut task["metadata"]["graphOs"]["terminalEvent"];
        event["scope"]["tenant"] = json!("physical-owner");
        event["kind"] = json!(kind);
        let text = decode(&task, TaskState::Completed).unwrap().text();
        assert!(text.contains("Caller tenant: tenant-one"));
        assert!(text.contains("Physical scope tenant: physical-owner"));
        assert!(text.contains(&format!("Kind: {kind}")));
    }
}

// spec: TUI-RUNTIME-R002.1.3.2.2.3
#[test]
fn result_reference_preserves_producer_limit() {
    let mut task = task();
    let reference = "r".repeat(4096);
    task["metadata"]["graphOs"]["terminalEvent"]["result_ref"] = json!(reference);
    assert!(
        decode(&task, TaskState::Completed)
            .unwrap()
            .text()
            .contains(&reference)
    );
}

// spec: TUI-RUNTIME-R002.1.3.2.2.3
#[test]
fn scope_digest_requires_exact_integer_bytes() {
    for digest in [
        json!("a".repeat(64)),
        json!(vec![0; 31]),
        json!(vec![0; 33]),
        json!(vec![256; 32]),
        json!(vec![-1; 32]),
        json!(vec![true; 32]),
        json!(vec![0.5; 32]),
    ] {
        let mut task = task();
        task["metadata"]["graphOs"]["terminalEvent"]["scope"]["identity_digest"] = digest;
        assert!(decode(&task, TaskState::Completed).is_err());
    }
}
