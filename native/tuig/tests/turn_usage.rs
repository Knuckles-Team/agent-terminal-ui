mod support;
use serde_json::json;
use tuig_native::{ArboraClient, TaskSubmission, turn_usage::TurnUsage};

// spec: TUIG-RUNTIME-R012.6.1
#[tokio::test]
async fn served_receipt_is_bound_and_missing_read_receipt_clears_usage() {
    let submission = TaskSubmission::new("Example").unwrap();
    let mut task = json!({"kind":"task","id":"native-work-item","contextId":"conversation",
        "status":{"state":"completed"},"metadata":{"arbora":{"runId":"admitted-run",
        "usage":{"taskId":"native-work-item","contextId":"conversation","runId":"admitted-run",
        "scope":"turn","counts":{"input_tokens":17,"output_tokens":0}}}},
        "artifacts":[{"parts":[{"kind":"text","text":"reply"}]}]});
    let response = json!({"jsonrpc":"2.0","id":submission.message_id(),"result":task});
    let (url, server) = support::serve("200 OK", &response.to_string()).await;
    let snapshot = ArboraClient::new(&url, Some("fixture-token"))
        .unwrap()
        .submit_task(&submission)
        .await
        .unwrap();
    assert!(!matches!(snapshot.usage, TurnUsage::Unavailable));
    assert!(
        server
            .await
            .unwrap()
            .to_lowercase()
            .contains("authorization: bearer fixture-token")
    );
    task["metadata"]["arbora"]
        .as_object_mut()
        .unwrap()
        .remove("usage");
    let response = json!({"jsonrpc":"2.0","id":"task-snapshot","result":task});
    let (url, server) = support::serve("200 OK", &response.to_string()).await;
    let read = ArboraClient::new(&url, Some("fixture-token"))
        .unwrap()
        .refresh_task(&snapshot.correlation)
        .await
        .unwrap();
    assert!(matches!(read.usage, TurnUsage::Unavailable));
    assert_eq!(read.output, snapshot.output);
    server.await.unwrap();
}

// spec: TUIG-RUNTIME-R012.6.1
#[tokio::test]
async fn foreign_usage_does_not_hide_valid_reply() {
    let submission = TaskSubmission::new("Example").unwrap();
    let response = json!({"jsonrpc":"2.0","id":submission.message_id(),"result":{
        "kind":"task","id":"task","contextId":"context","status":{"state":"completed"},
        "metadata":{"arbora":{"runId":"run","usage":{"taskId":"foreign","contextId":"context",
        "runId":"run","scope":"turn","counts":{"input_tokens":17}}}},
        "artifacts":[{"parts":[{"kind":"text","text":"valid reply"}]}]}});
    let (url, server) = support::serve("200 OK", &response.to_string()).await;
    let task = ArboraClient::new(&url, Some("fixture-token"))
        .unwrap()
        .submit_task(&submission)
        .await
        .unwrap();
    assert!(matches!(task.usage, TurnUsage::Unavailable));
    assert_eq!(task.output.text(), "Reply:\nvalid reply");
    server.await.unwrap();
}
