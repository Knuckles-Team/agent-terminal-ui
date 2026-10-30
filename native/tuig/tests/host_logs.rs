use serde_json::{Value, json};
use std::{
    sync::Arc,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
};
use tuig_native::{ArboraClient, app::run_host_terminal, host_logs::HostLogs};

const ENDPOINT_SENTINEL: &str = "http://127.0.0.1:1/";

fn receipt() -> Value {
    let expires = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_millis() as u64
        + 60000;
    json!({"version":1,"log_ref":"opaque","host_instance":"host","endpoint":"http://127.0.0.1:1/","workspace":"/fixture","tenant":"tenant","principal":"principal-π🙂","session_ref":"session","policy_revision":"policy","grant_revision":"grant","expires_at_ms":expires,"interface_mode":"both","web_logs":true,"ready":true,"source_generations":["host"]})
}

struct FixtureResponse {
    status: u16,
    body: Value,
}

fn response(status: u16, body: Value) -> FixtureResponse {
    FixtureResponse { status, body }
}

fn encode_response(fixture: FixtureResponse, endpoint: &str) -> String {
    let body = fixture
        .body
        .to_string()
        .replace(ENDPOINT_SENTINEL, endpoint);
    format!(
        "HTTP/1.1 {} Fixture\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        fixture.status,
        body.len()
    )
}

async fn serve(responses: Vec<FixtureResponse>) -> (ArboraClient, tokio::task::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let client = ArboraClient::new(
        &format!("http://{}", listener.local_addr().unwrap()),
        Some("fixture-token"),
    )
    .unwrap();
    let endpoint = client.endpoint();
    let server = tokio::spawn(async move {
        for fixture in responses {
            let response = encode_response(fixture, &endpoint);
            let (headers, body) = response.split_once("\r\n\r\n").unwrap();
            let declared_length: usize = headers
                .lines()
                .find_map(|line| {
                    let (key, value) = line.split_once(':')?;
                    key.eq_ignore_ascii_case("content-length")
                        .then(|| value.trim().parse().unwrap())
                })
                .unwrap();
            assert_eq!(declared_length, body.len());
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
                    assert!(headers.starts_with("POST /host/logs/"));
                    let body: Value = serde_json::from_str(body).unwrap();
                    if headers.starts_with("POST /host/logs/read") {
                        assert_eq!(body["log_ref"], "opaque");
                        assert_eq!(body["limit"], 128);
                        assert_eq!(body["version"], 2);
                    }
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

// spec: TUIG-RUNTIME-R002.11
#[tokio::test]
async fn authenticated_reads_clear_authority_after_denial_without_effect_replay() {
    let (client, server) = serve(vec![
        response(200, receipt()),
        response(
            200,
            json!({"version":2,"records":[{"host_instance":"host","sequence":7,"request":"original-request","timestamp":123.5,"severity":"WARN","message":"[literal]\u{1b}[31m"}],"cursor":"next","gap":true}),
        ),
        response(403, json!({})),
    ])
    .await;
    let mut reader = HostLogs::bind(Arc::new(client)).await.unwrap();
    let batch = reader.read().await.unwrap();
    assert_eq!(batch.records[0].message, "[literal][31m");
    assert_eq!(
        batch.records[0].display(),
        "[123.5 WARN host=host seq=7 request=original-request] [literal][31m"
    );
    assert!(batch.gap);
    assert!(reader.read().await.is_err());
    assert!(!reader.valid());
    assert!(reader.read().await.is_err());
    server.await.unwrap();
}

// spec: TUIG-RUNTIME-R002.11
#[tokio::test]
async fn disabled_expired_and_malformed_receipts_never_read() {
    for (key, value) in [
        ("web_logs", json!(false)),
        ("interface_mode", json!("web")),
        ("expires_at_ms", json!(0)),
        ("version", json!(true)),
        ("tenant", json!("")),
        ("endpoint", json!("")),
        ("source_generations", json!([])),
    ] {
        let mut payload = receipt();
        payload[key] = value;
        let (client, server) = serve(vec![response(200, payload)]).await;
        assert!(HostLogs::bind(Arc::new(client)).await.is_err());
        server.await.unwrap();
    }
}

// spec: TUIG-RUNTIME-R002.11
#[tokio::test]
async fn oversized_and_malformed_batches_invalidate_binding() {
    for payload in [
        json!({"records":[{"message":"x".repeat(16385)}],"cursor":null,"gap":false}),
        json!({"records":[],"gap":false}),
        json!({"records":[],"cursor":null,"gap":"false"}),
    ] {
        let (client, server) = serve(vec![response(200, receipt()), response(200, payload)]).await;
        let mut reader = HostLogs::bind(Arc::new(client)).await.unwrap();
        assert!(reader.read().await.is_err());
        assert!(!reader.valid());
        server.await.unwrap();
    }
}

// spec: TUIG-RUNTIME-R002.11
#[tokio::test]
async fn exact_retention_gap_stops_without_retry_and_other_conflicts_refuse() {
    use tuig_native::host_logs::{REFUSED, RETENTION_GAP};
    for (body, expected) in [
        (json!({"detail":"retention_gap"}), RETENTION_GAP),
        (json!({"detail":"other"}), REFUSED),
    ] {
        let (client, server) = serve(vec![response(200, receipt()), response(409, body)]).await;
        let mut reader = HostLogs::bind(Arc::new(client)).await.unwrap();
        assert_eq!(reader.read().await.err(), Some(expected));
        assert!(!reader.valid());
        assert_eq!(reader.read().await.err(), Some(REFUSED));
        server.await.unwrap();
    }
}

// spec: TUIG-RUNTIME-R002.2
#[tokio::test]
async fn changed_receipt_binding_is_rejected_before_reader_use() {
    let (client, server) = serve(vec![response(200, receipt())]).await;
    let client = Arc::new(client);
    let logs = HostLogs::bind(client.clone()).await.unwrap();
    let mut changed = receipt();
    changed["endpoint"] = json!(client.endpoint());
    changed["tenant"] = json!("foreign-tenant");
    let changed = tuig_native::host_logs::HostLaunchReceipt::parse(&changed).unwrap();
    let matching = logs.receipt().clone();
    let reader = logs.into_reader();
    assert!(run_host_terminal(changed, client.as_ref(), Some(reader)).is_err());
    assert!(matching.expires_at_ms() > 0);
    server.await.unwrap();
}

// spec: TUIG-RUNTIME-R002.3
#[tokio::test]
async fn adapter_reads_only_the_bound_opaque_reference() {
    let (client, server) = serve(vec![
        response(200, receipt()),
        response(
            200,
            json!({"version":2,"records":[],"cursor":null,"gap":false}),
        ),
    ])
    .await;
    let client = Arc::new(client);
    let logs = HostLogs::bind(client.clone()).await.unwrap();
    let receipt = logs.receipt().clone();
    let mut reader =
        run_host_terminal(receipt.clone(), client.as_ref(), Some(logs.into_reader())).unwrap();
    let batch = reader.read(&receipt.log_ref, None, 128).await.unwrap();
    assert!(batch.records.is_empty());
    server.await.unwrap();
}

// spec: TUIG-RUNTIME-R002.3
#[tokio::test]
async fn missing_reader_refuses_without_a_network_read() {
    let client = Arc::new(ArboraClient::new("http://127.0.0.1:9", Some("fixture-token")).unwrap());
    let mut payload = receipt();
    payload["endpoint"] = json!(client.endpoint());
    let receipt = tuig_native::host_logs::HostLaunchReceipt::parse(&payload).unwrap();
    assert!(run_host_terminal(receipt, client.as_ref(), None).is_err());
}

#[tokio::test]
async fn endpoint_binding_is_checked_before_reader_use() {
    let (client, server) = serve(vec![response(200, receipt())]).await;
    let client = Arc::new(client);
    let logs = HostLogs::bind(client.clone()).await.unwrap();
    let mut changed = receipt();
    changed["endpoint"] = json!("http://127.0.0.1:2/");
    let changed = tuig_native::host_logs::HostLaunchReceipt::parse(&changed).unwrap();
    assert!(run_host_terminal(changed, client.as_ref(), Some(logs.into_reader())).is_err());
    server.await.unwrap();
}

#[tokio::test]
async fn records_from_another_generation_are_refused() {
    let (client, server) = serve(vec![
        response(200, receipt()),
        response(
            200,
            json!({"version":2,"records":[{"host_instance":"foreign-host","sequence":1,"request":"request","timestamp":1.0,"severity":"INFO","message":"foreign"}],"cursor":null,"gap":false}),
        ),
    ])
    .await;
    let mut reader = HostLogs::bind(Arc::new(client)).await.unwrap();
    assert!(reader.read().await.is_err());
    assert!(!reader.valid());
    server.await.unwrap();
}
