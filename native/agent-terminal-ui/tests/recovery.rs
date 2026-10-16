use agent_terminal_ui_native::{
    GraphOsClient, correlation::TaskCorrelation, recovery::ReadFailure,
};
use serde_json::{Value, json};
use std::time::Duration;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
};

fn snapshot() -> Value {
    json!({"jsonrpc":"2.0", "id":"task-snapshot", "result": {
        "kind":"task", "id":"task-one", "contextId":"context-two",
        "metadata":{"graphOs":{"runId":"run-three"}}, "status":{"state":"working"}
    }})
}

fn response(status: u16, body: Value) -> String {
    let body = body.to_string();
    format!(
        "HTTP/1.1 {status} Fixture\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    )
}

async fn serve(responses: Vec<String>) -> (GraphOsClient, tokio::task::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let client = GraphOsClient::new(
        &format!("http://{}", listener.local_addr().unwrap()),
        Some("fixture-token"),
    )
    .unwrap();
    let server = tokio::spawn(async move {
        for response in responses {
            let (mut socket, _) = tokio::time::timeout(Duration::from_secs(2), listener.accept())
                .await
                .unwrap()
                .unwrap();
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
                    if body.len() < length {
                        continue;
                    }
                    assert!(
                        headers
                            .to_lowercase()
                            .contains("authorization: bearer fixture-token")
                    );
                    assert!(!headers.to_lowercase().contains("idempotency-key"));
                    assert_eq!(
                        serde_json::from_str::<Value>(body).unwrap(),
                        json!({
                            "jsonrpc":"2.0", "id":"task-snapshot", "method":"tasks/get", "params":{"id":"task-one"}
                        })
                    );
                    break;
                }
            }
            socket.write_all(response.as_bytes()).await.unwrap();
        }
        assert!(
            tokio::time::timeout(Duration::from_millis(400), listener.accept())
                .await
                .is_err(),
            "unexpected extra read or effect replay"
        );
    });
    (client, server)
}

// spec: TUI-RUNTIME-R002.1.3.2.1
#[tokio::test]
async fn disconnect_and_interrupted_body_recover_only_the_bound_read() {
    let original = snapshot();
    let mut refreshed = original.clone();
    refreshed["result"]["status"]["state"] = json!("completed");
    refreshed["result"]
        .as_object_mut()
        .unwrap()
        .remove("metadata");
    let (client, server) = serve(vec![
        response(200, original),
        String::new(),
        "HTTP/1.1 200 OK\r\nContent-Length: 999\r\nConnection: close\r\n\r\n{".into(),
        response(200, refreshed),
    ])
    .await;
    let initial = client.get_task("task-one").await.unwrap();
    let start = tokio::time::Instant::now();
    let recovered = client.refresh_task(&initial.correlation).await.unwrap();
    assert!(start.elapsed() >= Duration::from_millis(300));
    assert_eq!(recovered.correlation, initial.correlation);
    assert_eq!(
        recovered.state,
        agent_terminal_ui_native::correlation::TaskState::Completed
    );
    server.await.unwrap();
}

// spec: TUI-RUNTIME-R002.1.3.2.1
#[tokio::test]
async fn retries_stop_at_three_and_manual_read_can_recover() {
    let (client, server) = serve(vec![
        response(503, json!({})),
        response(502, json!({})),
        response(504, json!({})),
        response(200, snapshot()),
    ])
    .await;
    assert_eq!(
        client.read_task("task-one", None).await,
        Err(ReadFailure::Recoverable)
    );
    assert!(client.get_task("task-one").await.is_ok());
    server.await.unwrap();
}

// spec: TUI-RUNTIME-R002.1.3.2.1
#[tokio::test]
async fn denial_after_disconnect_stops_without_replay_and_can_be_refreshed() {
    for status in [401, 403, 404] {
        let original = snapshot();
        let binding = TaskCorrelation::from_task(&original["result"]).unwrap();
        let (client, server) = serve(vec![
            String::new(),
            response(status, json!({"secret":"protected"})),
            response(200, original),
        ])
        .await;
        assert_eq!(
            client.read_task("task-one", Some(&binding)).await,
            Err(ReadFailure::Refused)
        );
        assert_eq!(
            client.refresh_task(&binding).await.unwrap().correlation,
            binding
        );
        server.await.unwrap();
    }
}

// spec: TUI-RUNTIME-R002.1.3.2.1
#[tokio::test]
async fn rejects_changed_identity_and_never_acquires_a_later_run() {
    for path in [
        "/result/id",
        "/result/contextId",
        "/result/metadata/graphOs/runId",
        "/id",
    ] {
        let original = snapshot();
        let binding = TaskCorrelation::from_task(&original["result"]).unwrap();
        let mut changed = original;
        *changed.pointer_mut(path).unwrap() = json!("foreign");
        let (client, server) = serve(vec![response(200, changed)]).await;
        assert!(matches!(
            client.read_task("task-one", Some(&binding)).await,
            Err(ReadFailure::Invalid(_))
        ));
        server.await.unwrap();
    }
    let mut original = snapshot();
    original["result"]
        .as_object_mut()
        .unwrap()
        .remove("metadata");
    let binding = TaskCorrelation::from_task(&original["result"]).unwrap();
    let (client, server) = serve(vec![response(200, snapshot())]).await;
    assert_eq!(
        client.read_task("task-one", Some(&binding)).await,
        Err(ReadFailure::Invalid("Task correlation mismatch"))
    );
    server.await.unwrap();
}

// spec: TUI-RUNTIME-R002.1.3.2.1
#[tokio::test]
async fn rpc_refusal_does_not_retry_or_expose_server_detail() {
    let (client, server) = serve(vec![response(
        200,
        json!({"jsonrpc":"2.0", "id":"task-snapshot", "error":{"code":-32001,"message":"secret"}}),
    )])
    .await;
    let failure = client.read_task("task-one", None).await.unwrap_err();
    assert_eq!(failure, ReadFailure::Refused);
    assert!(!failure.message().contains("secret"));
    server.await.unwrap();
}

// spec: TUI-RUNTIME-R002.1.3.2.1
#[tokio::test]
async fn aborting_a_read_during_backoff_stops_owned_recovery() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let client =
        GraphOsClient::new(&format!("http://{}", listener.local_addr().unwrap()), None).unwrap();
    let request = tokio::spawn(async move { client.get_task("task-one").await });
    let (mut socket, _) = listener.accept().await.unwrap();
    let mut bytes = [0; 4096];
    assert!(socket.read(&mut bytes).await.unwrap() > 0);
    socket
        .write_all(response(503, json!({})).as_bytes())
        .await
        .unwrap();
    drop(socket);
    tokio::time::sleep(Duration::from_millis(30)).await;
    request.abort();
    assert!(request.await.unwrap_err().is_cancelled());
    assert!(
        tokio::time::timeout(Duration::from_millis(400), listener.accept())
            .await
            .is_err()
    );
}

// spec: TUI-RUNTIME-R002.1.3.2.1
#[tokio::test]
async fn total_deadline_bounds_unresponsive_reads() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let client =
        GraphOsClient::new(&format!("http://{}", listener.local_addr().unwrap()), None).unwrap();
    let start = tokio::time::Instant::now();
    let request = tokio::spawn(async move { client.read_task("task-one", None).await });
    let (_first, _) = listener.accept().await.unwrap();
    let (_second, _) = tokio::time::timeout(Duration::from_secs(11), listener.accept())
        .await
        .unwrap()
        .unwrap();
    assert_eq!(
        tokio::time::timeout(Duration::from_secs(3), request)
            .await
            .unwrap()
            .unwrap(),
        Err(ReadFailure::Recoverable)
    );
    assert!(start.elapsed() >= Duration::from_secs(12));
    assert!(start.elapsed() < Duration::from_secs(13));
    assert!(
        tokio::time::timeout(Duration::from_millis(400), listener.accept())
            .await
            .is_err()
    );
}
