use serde_json::{Value, json};
use tuig_native::correlation::{TaskCorrelation, TaskEvent, TaskState};

fn events() -> Vec<Value> {
    serde_json::from_str(include_str!(
        "../../../tests/fixtures/a2a_task_correlation.json"
    ))
    .unwrap()
}

// spec: TUIG-RUNTIME-R002.1.1
#[test]
fn shared_wire_events_preserve_distinct_server_identifiers() {
    let events = events();
    let binding = TaskCorrelation::from_task(&events[0]).unwrap();
    assert_eq!(binding.task_id(), "server-task-1");
    assert_eq!(binding.context_id(), "server-context-2");
    assert_eq!(binding.run_id(), Some("server-run-3"));
    let before = binding.clone();
    assert_eq!(
        binding.validate(&events[1]).unwrap(),
        TaskEvent::Status {
            state: TaskState::Working,
            final_event: false,
        }
    );
    assert_eq!(
        binding.validate(&events[2]).unwrap(),
        TaskEvent::Text("the answer".into())
    );
    assert_eq!(
        binding.validate(&events[3]).unwrap(),
        TaskEvent::Status {
            state: TaskState::Completed,
            final_event: true,
        }
    );
    assert_eq!(binding, before);
}

// spec: TUIG-RUNTIME-R002.1.1
#[test]
fn missing_run_remains_unavailable_and_is_never_inferred() {
    let mut initial = events()[0].clone();
    initial.as_object_mut().unwrap().remove("metadata");
    let binding = TaskCorrelation::from_task(&initial).unwrap();
    assert_eq!(binding.run_id(), None);
    assert!(binding.validate(&events()[2]).is_ok());
    assert!(binding.validate(&events()[1]).is_err());
    assert_eq!(binding.run_id(), None);
}

// spec: TUIG-RUNTIME-R002.1.1
#[test]
fn missing_invalid_and_conflicting_identifiers_are_refused() {
    let fixture = events();
    let binding = TaskCorrelation::from_task(&fixture[0]).unwrap();
    let before = binding.clone();
    for key in ["id", "contextId"] {
        for invalid in [Value::Null, json!(""), json!("\n"), json!(42)] {
            let mut initial = fixture[0].clone();
            initial[key] = invalid;
            assert!(TaskCorrelation::from_task(&initial).is_err());
        }
        let mut initial = fixture[0].clone();
        initial.as_object_mut().unwrap().remove(key);
        assert!(TaskCorrelation::from_task(&initial).is_err());
    }
    for pointer in ["/taskId", "/contextId", "/metadata/arbora/runId"] {
        for invalid in [Value::Null, json!(""), json!(false), json!("foreign-id")] {
            let mut event = fixture[1].clone();
            *event.pointer_mut(pointer).unwrap() = invalid;
            assert!(binding.validate(&event).is_err(), "{pointer}");
        }
    }
    for key in ["taskId", "contextId"] {
        let mut event = fixture[1].clone();
        event.as_object_mut().unwrap().remove(key);
        assert!(binding.validate(&event).is_err());
    }
    let mut event = fixture[1].clone();
    event["id"] = json!("foreign-alias");
    assert!(binding.validate(&event).is_err());
    assert_eq!(binding, before);
}

// spec: TUIG-RUNTIME-R002.1.1
#[test]
fn malformed_and_unsupported_events_are_refused_without_mutation() {
    let fixture = events();
    let binding = TaskCorrelation::from_task(&fixture[0]).unwrap();
    let before = binding.clone();
    for (key, invalid) in [
        ("kind", json!("message")),
        ("kind", Value::Null),
        ("status", json!({"state":"unknown"})),
        ("status", json!([])),
        ("final", json!("true")),
        ("metadata", json!([])),
        ("metadata", json!({"arbora":false})),
    ] {
        let mut event = fixture[1].clone();
        event[key] = invalid;
        assert!(binding.validate(&event).is_err());
    }
    for invalid in [
        json!([]),
        json!([{"kind":"file","uri":"x"}]),
        json!([{"kind":"text","text":42}]),
        json!([null]),
    ] {
        let mut event = fixture[2].clone();
        event["artifact"]["parts"] = invalid;
        assert!(binding.validate(&event).is_err());
    }
    assert!(binding.validate(&Value::Null).is_err());
    assert!(TaskCorrelation::from_task(&fixture[1]).is_err());
    assert_eq!(binding, before);
}
