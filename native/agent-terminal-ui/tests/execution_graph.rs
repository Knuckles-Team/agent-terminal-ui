use agent_terminal_ui_native::{
    ArboraClient, AuthMode, correlation::TaskCorrelation, execution_graph::SCHEMA,
    run_inspector::ReadRefusal,
};
use serde_json::{Value, json};
use std::time::Duration;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
    task::JoinHandle,
};

fn payload() -> Value {
    serde_json::from_str::<Value>(include_str!("fixtures/execution_graph_contract.json")).unwrap()["value"].clone()
}

fn binding() -> TaskCorrelation {
    let value = payload();
    TaskCorrelation::from_task(
        &json!({"kind":"task", "id":value["task_id"], "contextId":"context-one",
        "status":{"state":"working"}, "metadata":{"arbora":{"runId":value["run_id"]}}}),
    )
    .unwrap()
}

fn registry(ops: Value) -> Value {
    json!({"api_version":"v1", "registry_digest":"fixture-digest", "ops":ops})
}

fn envelope() -> Value {
    json!({"ok":true, "meta":{"api_version":"v1", "registry_digest":"fixture-digest"}, "result":{"value":payload()}})
}

async fn server(responses: Vec<(u16, Value)>) -> (String, JoinHandle<Vec<String>>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let endpoint = format!("http://{}", listener.local_addr().unwrap());
    let task = tokio::spawn(async move {
        let mut requests = Vec::new();
        for (status, body) in responses {
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut bytes = Vec::new();
            loop {
                let mut buffer = [0; 4096];
                let count = socket.read(&mut buffer).await.unwrap();
                assert!(count > 0);
                bytes.extend_from_slice(&buffer[..count]);
                assert!(bytes.len() < 65536);
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
            socket.write_all(format!("HTTP/1.1 {status} Test\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len()).as_bytes()).await.unwrap();
        }
        assert!(
            tokio::time::timeout(Duration::from_millis(50), listener.accept())
                .await
                .is_err(),
            "Unexpected retry or fallback request"
        );
        requests
    });
    (endpoint, task)
}

// spec: TUI-RUNTIME-R010.11
#[tokio::test]
async fn public_client_reads_only_advertised_graph_without_summary_prerequisite() {
    for anonymous in [false, true] {
        let (endpoint, requests) = server(vec![
            (200, registry(json!([{"id":"runs.execution_graph"}]))),
            (200, envelope()),
        ])
        .await;
        let client = if anonymous {
            ArboraClient::with_auth_mode(&endpoint, None, AuthMode::None)
        } else {
            ArboraClient::new(&endpoint, Some("fixture-token"))
        }
        .unwrap();
        let bound = binding();
        let graph =
            tokio::time::timeout(Duration::from_secs(2), client.get_execution_graph(&bound))
                .await
                .unwrap()
                .unwrap();
        assert_eq!(graph.edges.len(), 4);
        let requests = requests.await.unwrap();
        assert_eq!(requests.len(), 2);
        assert!(requests[0].starts_with("GET /api/v1/registry "));
        assert!(requests[1].starts_with("POST /api/v1/ops/runs.execution_graph "));
        for request in &requests {
            assert_eq!(
                request
                    .to_lowercase()
                    .contains("authorization: bearer fixture-token"),
                !anonymous
            );
        }
        let body: Value =
            serde_json::from_str(requests[1].split_once("\r\n\r\n").unwrap().1).unwrap();
        assert_eq!(
            body,
            json!({"schema_version":SCHEMA, "run_id":bound.run_id().unwrap(), "task_id":bound.task_id()})
        );
    }
}

// spec: TUI-RUNTIME-R010.11
#[tokio::test]
async fn absent_operation_denied_or_malformed_registry_never_posts() {
    for (status, body, expected) in [
        (
            200,
            registry(json!([{"id":"runs.get"}])),
            ReadRefusal::Unavailable,
        ),
        (200, registry(json!([])), ReadRefusal::Unavailable),
        (
            200,
            json!({"api_version":"v2", "registry_digest":"fixture-digest", "ops":[{"id":"runs.execution_graph"}]}),
            ReadRefusal::Unavailable,
        ),
        (
            200,
            json!({"api_version":"v1", "ops":[{"id":"runs.execution_graph"}]}),
            ReadRefusal::Unavailable,
        ),
        (403, json!({"detail":"denied"}), ReadRefusal::Denied),
    ] {
        let (endpoint, requests) = server(vec![(status, body)]).await;
        let client = ArboraClient::new(&endpoint, Some("fixture-token")).unwrap();
        assert_eq!(client.get_execution_graph(&binding()).await, Err(expected));
        let requests = requests.await.unwrap();
        assert_eq!(requests.len(), 1);
        assert!(requests[0].starts_with("GET /api/v1/registry "));
    }
}

// spec: TUI-RUNTIME-R010.11
#[tokio::test]
async fn denied_wrong_digest_and_malformed_graph_do_not_fall_back() {
    let mut bad_digest = envelope();
    bad_digest["meta"]["registry_digest"] = json!("different");
    let mut wrong_owner = envelope();
    wrong_owner["result"]["value"]["task_id"] = json!("first");
    let mut private = envelope();
    private["result"]["value"]["snapshot"]["thoughts"] = json!("not public");
    for (status, body, expected) in [
        (403, json!({"detail":"denied"}), ReadRefusal::Denied),
        (200, bad_digest, ReadRefusal::Unavailable),
        (200, wrong_owner, ReadRefusal::WrongRun),
        (200, private, ReadRefusal::Unavailable),
        (200, json!({}), ReadRefusal::Unavailable),
    ] {
        let (endpoint, requests) = server(vec![
            (
                200,
                registry(json!([{"id":"runs.execution_graph"}, {"id":"runs.get"}])),
            ),
            (status, body),
        ])
        .await;
        let client = ArboraClient::new(&endpoint, Some("fixture-token")).unwrap();
        assert_eq!(client.get_execution_graph(&binding()).await, Err(expected));
        let requests = requests.await.unwrap();
        assert_eq!(requests.len(), 2);
        assert!(requests[1].starts_with("POST /api/v1/ops/runs.execution_graph "));
    }
}

// spec: TUI-RUNTIME-R010.11
#[tokio::test]
async fn unbound_or_unauthenticated_client_makes_zero_requests() {
    let (endpoint, requests) = server(vec![]).await;
    let client = ArboraClient::new(&endpoint, None).unwrap();
    assert_eq!(
        client.get_execution_graph(&binding()).await,
        Err(ReadRefusal::Denied)
    );
    let bound = TaskCorrelation::from_task(
        &json!({"kind":"task", "id":"root", "contextId":"context", "status":{"state":"working"}}),
    )
    .unwrap();
    let client = ArboraClient::new(&endpoint, Some("fixture-token")).unwrap();
    assert_eq!(
        client.get_execution_graph(&bound).await,
        Err(ReadRefusal::Unavailable)
    );
    assert!(requests.await.unwrap().is_empty());
}
