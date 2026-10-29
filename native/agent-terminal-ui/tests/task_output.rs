mod support;

use agent_terminal_ui_native::{ArboraClient, TaskSubmission, task_output::TaskOutput};
use serde_json::{Value, json};
use support::serve;

fn completed(request_id: &str) -> Value {
    json!({
        "jsonrpc":"2.0", "id":request_id,
        "result":{
            "kind":"task", "id":"task-one", "contextId":"context-two",
            "status":{"state":"completed"},
            "metadata":{"arbora":{"runId":"run-three"}},
            "artifacts":[{"artifactId":"reply","parts":[
                {"kind":"text","text":"Actual "},{"kind":"text","text":"reply 界"}
            ]}]
        }
    })
}

// spec: TUIG-RUNTIME-R002.1.3.2.2.2.1
#[tokio::test]
async fn authenticated_submission_and_task_read_keep_the_returned_reply() {
    let submission = TaskSubmission::new("Read the example").unwrap();
    let (url, server) = serve("200 OK", &completed(submission.message_id()).to_string()).await;
    let snapshot = ArboraClient::new(&url, Some("fixture-token"))
        .unwrap()
        .submit_task(&submission)
        .await
        .unwrap();
    assert_eq!(snapshot.output, TaskOutput::Text("Actual reply 界".into()));
    assert_eq!(snapshot.correlation.task_id(), "task-one");
    let request = server.await.unwrap();
    assert!(
        request
            .to_lowercase()
            .contains("authorization: bearer fixture-token")
    );
    let (_, body) = request.split_once("\r\n\r\n").unwrap();
    assert_eq!(
        serde_json::from_str::<Value>(body).unwrap()["method"],
        "message/send"
    );

    let (url, server) = serve("200 OK", &completed("task-snapshot").to_string()).await;
    let refreshed = ArboraClient::new(&url, Some("fixture-token"))
        .unwrap()
        .refresh_task(&snapshot.correlation)
        .await
        .unwrap();
    assert_eq!(refreshed.output, snapshot.output);
    let request = server.await.unwrap();
    let (_, body) = request.split_once("\r\n\r\n").unwrap();
    assert_eq!(
        serde_json::from_str::<Value>(body).unwrap()["method"],
        "tasks/get"
    );
}

// spec: TUIG-RUNTIME-R002.1.3.2.2.2.1
#[tokio::test]
async fn foreign_or_invalid_artifacts_cannot_be_returned_for_display() {
    for (path, value) in [
        ("/result/id", json!("foreign-task")),
        ("/result/contextId", json!("foreign-context")),
        ("/result/metadata/arbora/runId", json!("foreign-run")),
        ("/result/artifacts/0/parts/0/text", json!(42)),
        ("/result/artifacts/0/parts/0/kind", json!("file")),
    ] {
        let initial = completed("task-snapshot");
        let binding =
            agent_terminal_ui_native::correlation::TaskCorrelation::from_task(&initial["result"])
                .unwrap();
        let mut response = initial;
        *response.pointer_mut(path).unwrap() = value;
        let (url, server) = serve("200 OK", &response.to_string()).await;
        assert!(
            ArboraClient::new(&url, Some("fixture-token"))
                .unwrap()
                .refresh_task(&binding)
                .await
                .is_err()
        );
        server.await.unwrap();
    }
}
