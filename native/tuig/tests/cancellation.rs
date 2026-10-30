mod support;

use serde_json::{Value, json};
use std::time::Duration;
use support::{serve, serve_raw};
use tokio::{io::AsyncReadExt, net::TcpListener};
use tuig_native::{
    ArboraClient,
    correlation::{TaskCorrelation, TaskState},
};

fn acknowledgement() -> Value {
    json!({
        "jsonrpc": "2.0",
        "id": "task-cancel",
        "result": {
            "kind": "task",
            "id": "task-1",
            "contextId": "context-2",
            "metadata": {"arbora": {"runId": "run-3"}},
            "status": {"state": "canceled"}
        }
    })
}

fn binding() -> TaskCorrelation {
    TaskCorrelation::from_task(&acknowledgement()["result"]).unwrap()
}

// spec: TUIG-RUNTIME-R002.1.5
#[tokio::test]
async fn cancellation_requires_authenticated_matching_server_acknowledgement() {
    for include_run in [true, false] {
        let mut response = acknowledgement();
        if !include_run {
            response["result"]
                .as_object_mut()
                .unwrap()
                .remove("metadata");
        }
        let (url, server) = serve("200 OK", &response.to_string()).await;
        let task = ArboraClient::new(&url, Some("fixture-token"))
            .unwrap()
            .cancel_task(&binding())
            .await
            .unwrap();
        assert_eq!(task.correlation, binding());
        assert_eq!(task.correlation.run_id(), Some("run-3"));
        assert_eq!(task.state, TaskState::Canceled);
        let request = server.await.unwrap();
        assert!(request.starts_with("POST /a2a HTTP/1.1\r\n"));
        let (headers, body) = request.split_once("\r\n\r\n").unwrap();
        assert!(
            headers
                .to_lowercase()
                .contains("authorization: bearer fixture-token")
        );
        assert!(!headers.to_lowercase().contains("idempotency-key"));
        assert_eq!(
            serde_json::from_str::<Value>(body).unwrap(),
            json!({
                "jsonrpc": "2.0", "id": "task-cancel",
                "method": "tasks/cancel", "params": {"id": "task-1"}
            })
        );
    }
}

// spec: TUIG-RUNTIME-R002.1.5
#[tokio::test]
async fn cancellation_refuses_non_canceled_mismatched_and_malformed_results() {
    let mut responses = vec![json!(null), json!({}), json!([])];
    for state in [
        "submitted",
        "working",
        "input-required",
        "auth-required",
        "completed",
        "failed",
        "rejected",
    ] {
        let mut response = acknowledgement();
        response["result"]["status"]["state"] = json!(state);
        responses.push(response);
    }
    for (path, value) in [
        ("/jsonrpc", json!("1.0")),
        ("/id", json!("task-snapshot")),
        ("/result/id", json!("other-task")),
        ("/result/contextId", json!("other-context")),
        ("/result/kind", json!("status-update")),
        ("/result/status/state", json!("unknown")),
        ("/result/metadata/arbora/runId", json!("other-run")),
        ("/result/metadata/arbora/runId", json!(null)),
    ] {
        let mut response = acknowledgement();
        *response.pointer_mut(path).unwrap() = value;
        responses.push(response);
    }
    let mut response = acknowledgement();
    response["error"] = json!({"code": -32001, "message": "secret-server-detail"});
    responses.push(response);
    let mut response = acknowledgement();
    response.as_object_mut().unwrap().remove("result");
    responses.push(response);
    for response in responses {
        let (url, server) = serve("200 OK", &response.to_string()).await;
        let error = ArboraClient::new(&url, None)
            .unwrap()
            .cancel_task(&binding())
            .await
            .unwrap_err();
        assert!(!error.contains("secret-server-detail"));
        assert!(!error.contains("other-"));
        server.await.unwrap();
    }
}

// spec: TUIG-RUNTIME-R002.1.5
#[tokio::test]
async fn cancellation_preserves_absent_run_and_refuses_new_run() {
    let mut response = acknowledgement();
    response["result"]
        .as_object_mut()
        .unwrap()
        .remove("metadata");
    let unbound_run = TaskCorrelation::from_task(&response["result"]).unwrap();
    let (url, server) = serve("200 OK", &response.to_string()).await;
    let task = ArboraClient::new(&url, None)
        .unwrap()
        .cancel_task(&unbound_run)
        .await
        .unwrap();
    assert_eq!(task.correlation.run_id(), None);
    server.await.unwrap();
    let (url, server) = serve("200 OK", &acknowledgement().to_string()).await;
    assert!(
        ArboraClient::new(&url, None)
            .unwrap()
            .cancel_task(&unbound_run)
            .await
            .is_err()
    );
    server.await.unwrap();
}

// spec: TUIG-RUNTIME-R002.1.5
#[tokio::test]
async fn cancellation_refuses_http_failure_redirect_invalid_json_and_oversized_response() {
    for status in [
        "401 Unauthorized",
        "403 Forbidden",
        "404 Not Found",
        "500 Internal Server Error",
        "302 Found",
        "200 OK",
    ] {
        let (url, server) = serve(status, "secret-server-detail").await;
        let error = ArboraClient::new(&url, None)
            .unwrap()
            .cancel_task(&binding())
            .await
            .unwrap_err();
        assert!(!error.contains("secret-server-detail"));
        server.await.unwrap();
    }
    let (url, server) = serve("200 OK", &"x".repeat(1024 * 1024 + 1)).await;
    assert_eq!(
        ArboraClient::new(&url, None)
            .unwrap()
            .cancel_task(&binding())
            .await
            .unwrap_err(),
        "Arbora task snapshot exceeds size limit"
    );
    server.await.unwrap();
}

// spec: TUIG-RUNTIME-R002.1.5
#[tokio::test]
async fn interrupted_cancellation_is_not_acknowledged_or_retried() {
    for response in ["", "HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n{"] {
        let (url, server) = serve_raw(response.to_owned()).await;
        assert!(
            ArboraClient::new(&url, None)
                .unwrap()
                .cancel_task(&binding())
                .await
                .is_err()
        );
        server.await.unwrap();
    }
}

// spec: TUIG-RUNTIME-R002.1.5
#[tokio::test]
async fn timed_out_cancellation_has_unknown_outcome_without_retry() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let client =
        ArboraClient::new(&format!("http://{}", listener.local_addr().unwrap()), None).unwrap();
    let server = async {
        let (mut socket, _) = tokio::time::timeout(Duration::from_secs(2), listener.accept())
            .await
            .unwrap()
            .unwrap();
        let mut buffer = [0; 4096];
        assert!(
            tokio::time::timeout(Duration::from_secs(2), socket.read(&mut buffer))
                .await
                .unwrap()
                .unwrap()
                > 0
        );
        assert!(
            tokio::time::timeout(Duration::from_secs(11), listener.accept())
                .await
                .is_err(),
            "timed out cancellation must never retry"
        );
        drop(socket);
    };
    let request = async {
        let started = tokio::time::Instant::now();
        let error = tokio::time::timeout(Duration::from_secs(12), client.cancel_task(&binding()))
            .await
            .expect("production cancellation timeout must remain bounded")
            .unwrap_err();
        assert!(started.elapsed() >= Duration::from_secs(10));
        assert_eq!(error, "Arbora cancellation outcome unknown");
    };
    tokio::join!(server, request);
}
