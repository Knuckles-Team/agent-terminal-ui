use agent_terminal_ui_native::{ArboraClient, correlation::TaskState};
use serde_json::{Value, json};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
};

async fn serve(status: &str, body: &str) -> (String, tokio::task::JoinHandle<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    let response = format!(
        "HTTP/1.1 {status}\r\nLocation: /redirected\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let server = tokio::spawn(async move {
        let (mut socket, _) = listener.accept().await.unwrap();
        let mut request = Vec::new();
        loop {
            let mut buffer = [0; 4096];
            let count = socket.read(&mut buffer).await.unwrap();
            assert!(count > 0);
            request.extend_from_slice(&buffer[..count]);
            let text = String::from_utf8_lossy(&request);
            if let Some((headers, body)) = text.split_once("\r\n\r\n") {
                let length: usize = headers
                    .lines()
                    .find_map(|line| {
                        let (key, value) = line.split_once(':')?;
                        key.eq_ignore_ascii_case("content-length")
                            .then(|| value.trim().parse().unwrap())
                    })
                    .unwrap();
                if body.len() >= length {
                    break;
                }
            }
        }
        let _ = socket.write_all(response.as_bytes()).await;
        String::from_utf8(request).unwrap()
    });
    (url, server)
}

fn snapshot() -> Value {
    json!({
        "jsonrpc": "2.0",
        "id": "task-snapshot",
        "result": {
            "kind": "task",
            "id": "task-1",
            "contextId": "context-2",
            "metadata": {"arbora": {"runId": "run-3"}},
            "status": {"state": "working"}
        }
    })
}

// spec: TUI-RUNTIME-R002.1.2
#[tokio::test]
async fn reads_task_snapshot_over_authenticated_json_rpc() {
    for include_run in [true, false] {
        let mut response = snapshot();
        if !include_run {
            response["result"]
                .as_object_mut()
                .unwrap()
                .remove("metadata");
        }
        let (url, server) = serve("200 OK", &response.to_string()).await;
        let task = ArboraClient::new(&url, Some("fixture-token"))
            .unwrap()
            .get_task("task-1")
            .await
            .unwrap();
        assert_eq!(task.correlation.task_id(), "task-1");
        assert_eq!(task.correlation.context_id(), "context-2");
        assert_eq!(task.correlation.run_id(), include_run.then_some("run-3"));
        assert_eq!(task.state, TaskState::Working);
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
                "jsonrpc": "2.0", "id": "task-snapshot",
                "method": "tasks/get", "params": {"id": "task-1", "includeCommittedEvent": true}
            })
        );
    }
}

// spec: TUI-RUNTIME-R002.1.2
#[tokio::test]
async fn rejects_invalid_task_ids_before_network() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let client =
        ArboraClient::new(&format!("http://{}", listener.local_addr().unwrap()), None).unwrap();
    for task_id in ["", " ", "task\n1", &"x".repeat(81)] {
        assert_eq!(
            client.get_task(task_id).await.unwrap_err(),
            "Invalid task identifier"
        );
    }
    assert!(
        tokio::time::timeout(std::time::Duration::from_millis(20), listener.accept())
            .await
            .is_err()
    );
}

// spec: TUI-RUNTIME-R002.1.2
#[tokio::test]
async fn rejects_malformed_mismatched_and_error_envelopes() {
    let mut responses = vec![json!(null), json!({}), json!([])];
    for (path, value) in [
        ("/jsonrpc", json!("1.0")),
        ("/id", json!("wrong-request")),
        ("/id", json!(null)),
        ("/result/id", json!("other-task")),
        ("/result/contextId", json!("")),
        ("/result/kind", json!("status-update")),
        ("/result/status/state", json!("unknown")),
        ("/result/metadata/arbora/runId", json!(null)),
    ] {
        let mut response = snapshot();
        *response.pointer_mut(path).unwrap() = value;
        responses.push(response);
    }
    let mut response = snapshot();
    response["error"] = json!({"code": -32001, "message": "secret-server-detail"});
    responses.push(response);
    let mut response = snapshot();
    response.as_object_mut().unwrap().remove("result");
    responses.push(response);
    for response in responses {
        let (url, server) = serve("200 OK", &response.to_string()).await;
        let error = ArboraClient::new(&url, None)
            .unwrap()
            .get_task("task-1")
            .await
            .unwrap_err();
        assert!(!error.contains("secret-server-detail"));
        assert!(!error.contains("other-task"));
        server.await.unwrap();
    }
}

// spec: TUI-RUNTIME-R002.1.2
#[tokio::test]
async fn rejects_http_failure_redirect_unknown_task_and_invalid_json() {
    for status in [
        "401 Unauthorized",
        "404 Not Found",
        "500 Internal Server Error",
        "302 Found",
        "200 OK",
    ] {
        let (url, server) = serve(status, "secret-server-detail").await;
        let error = ArboraClient::new(&url, None)
            .unwrap()
            .get_task("task-1")
            .await
            .unwrap_err();
        assert!(!error.contains("secret-server-detail"));
        if status != "200 OK" {
            assert_eq!(error, "Arbora task read refused or unavailable");
        }
        server.await.unwrap();
    }
}

// spec: TUI-RUNTIME-R002.1.2
#[tokio::test]
async fn bounds_snapshot_response_size() {
    let (url, server) = serve("200 OK", &"x".repeat(1024 * 1024 + 1)).await;
    assert_eq!(
        ArboraClient::new(&url, None)
            .unwrap()
            .get_task("task-1")
            .await
            .unwrap_err(),
        "Arbora task snapshot exceeds size limit"
    );
    server.await.unwrap();
}

// spec: TUI-RUNTIME-R002.1.3.2.2.3
#[tokio::test]
async fn point_read_preserves_identity_and_rejects_retained_binding_mismatch() {
    let mut response = snapshot();
    response["result"]["status"]["state"] = json!("completed");
    response["result"]["metadata"]["arbora"]["terminalEvent"] = json!({
        "status":"available", "tenant":"tenant", "scope":{"tenant":"tenant",
        "scope":{"kind":"graph","graph":"graph"},"incarnation_id":"incarnation","identity_digest":vec![170;32]},
        "batch_id":"batch", "commit_sequence":7,"ordinal":0,"run_id":"run-3","kind":"outcome",
        "outcome":"succeeded","result_ref":null,"payload_digest":"b".repeat(64)
    });
    let (url, server) = serve("200 OK", &response.to_string()).await;
    let task = ArboraClient::new(&url, Some("fixture-token"))
        .unwrap()
        .get_task("task-1")
        .await
        .unwrap();
    assert!(task.terminal_event.text().contains("Commit sequence: 7"));
    assert!(server.await.unwrap().contains("includeCommittedEvent"));
    let mut unbound = response["result"].clone();
    unbound["metadata"]["arbora"]
        .as_object_mut()
        .unwrap()
        .remove("runId");
    let binding =
        agent_terminal_ui_native::correlation::TaskCorrelation::from_task(&unbound).unwrap();
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

// spec: TUI-RUNTIME-R002.1.3.2.2.3
#[tokio::test]
async fn point_read_omission_and_refusal_remain_unavailable_over_http() {
    for reason in [None, Some("legacy_unbound"), Some("producer_unavailable")] {
        let mut response = snapshot();
        if let Some(reason) = reason {
            response["result"]["metadata"]["arbora"]["terminalEvent"] =
                json!({"status":"unavailable", "reason":reason});
        }
        let (url, server) = serve("200 OK", &response.to_string()).await;
        let task = ArboraClient::new(&url, Some("fixture-token"))
            .unwrap()
            .get_task("task-1")
            .await
            .unwrap();
        assert_eq!(task.correlation.run_id(), Some("run-3"));
        let text = task.terminal_event.text();
        assert!(text.contains("unavailable"));
        assert!(!text.contains("Commit sequence:"));
        let request = server.await.unwrap();
        let (headers, body) = request.split_once("\r\n\r\n").unwrap();
        assert!(
            headers
                .to_lowercase()
                .contains("authorization: bearer fixture-token")
        );
        let body: Value = serde_json::from_str(body).unwrap();
        assert_eq!(body["method"], "tasks/get");
        assert_eq!(
            body["params"],
            json!({"id":"task-1", "includeCommittedEvent":true})
        );
    }
}

// spec: TUI-RUNTIME-R002.1.3.2.2.3
#[tokio::test]
async fn point_read_malformed_projection_refuses_the_whole_http_snapshot() {
    for event in [
        Value::Null,
        json!({"status":"available"}),
        json!({"status":"unavailable", "reason":"unknown"}),
        json!({"status":"unavailable", "reason":"legacy_unbound", "cursor":"invented"}),
        json!({"status":"unavailable", "reason":"x".repeat(16_385)}),
    ] {
        let mut response = snapshot();
        response["result"]["metadata"]["arbora"]["terminalEvent"] = event;
        let (url, server) = serve("200 OK", &response.to_string()).await;
        let result = ArboraClient::new(&url, Some("fixture-token"))
            .unwrap()
            .get_task("task-1")
            .await;
        assert!(result.is_err());
        let request = server.await.unwrap();
        let (_, body) = request.split_once("\r\n\r\n").unwrap();
        let body: Value = serde_json::from_str(body).unwrap();
        assert_eq!(body["method"], "tasks/get");
    }
}
