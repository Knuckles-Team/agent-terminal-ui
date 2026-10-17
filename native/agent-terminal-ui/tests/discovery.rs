use agent_terminal_ui_native::ArboraClient;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
};

async fn serve(status: &str, body: &str) -> (String, tokio::task::JoinHandle<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    let location = if status.starts_with("302") {
        "Location: /redirected\r\n"
    } else {
        ""
    };
    let response = format!(
        "HTTP/1.1 {status}\r\n{location}Content-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let server = tokio::spawn(async move {
        let (mut socket, _) = listener.accept().await.unwrap();
        let mut request = vec![0; 4096];
        let n = socket.read(&mut request).await.unwrap();
        let _ = socket.write_all(response.as_bytes()).await;
        String::from_utf8_lossy(&request[..n]).into_owned()
    });
    (url, server)
}

// spec: TUI-RUNTIME-R002.7
#[tokio::test]
async fn reads_real_http_card_with_caller_credential() {
    let (url, server) = serve("200 OK", r#"{"name":"Arbora"}"#).await;
    assert_eq!(
        ArboraClient::new(&url, Some("fixture-token"))
            .unwrap()
            .discover()
            .await
            .unwrap(),
        "Arbora"
    );
    let request = server.await.unwrap();
    assert!(request.starts_with("GET /.well-known/agent-card.json HTTP/1.1"));
    assert!(
        request
            .to_lowercase()
            .contains("authorization: bearer fixture-token")
    );
}

// spec: TUI-RUNTIME-R002.7
#[tokio::test]
async fn refuses_http_errors_redirects_and_malformed_cards() {
    for (status, body) in [
        ("401 Unauthorized", "secret-body"),
        ("302 Found", "secret-body"),
        ("200 OK", "not-json"),
        ("200 OK", "{}"),
    ] {
        let (url, server) = serve(status, body).await;
        let error = ArboraClient::new(&url, None)
            .unwrap()
            .discover()
            .await
            .unwrap_err();
        assert!(!error.contains(body));
        if status != "200 OK" {
            assert_eq!(error, "Arbora discovery refused or unavailable");
        }
        server.await.unwrap();
    }
}

// spec: TUI-RUNTIME-R002.7
#[test]
fn rejects_unsafe_configuration_without_network() {
    for url in [
        "http://example.com",
        "https://user:secret@example.com",
        "https://example.com/path",
        "https://example.com?token=secret",
        "http://localhost:0",
        " https://example.com",
    ] {
        assert!(ArboraClient::new(url, Some("fixture-token")).is_err());
    }
    assert!(ArboraClient::new("https://example.com", None).is_err());
    assert!(ArboraClient::new("https://example.com", Some("bad\ncredential")).is_err());
}

// spec: TUI-RUNTIME-R002.7
#[tokio::test]
async fn cancels_pending_local_discovery() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let client =
        ArboraClient::new(&format!("http://{}", listener.local_addr().unwrap()), None).unwrap();
    let request = tokio::spawn(async move { client.discover().await });
    let (mut socket, _) = listener.accept().await.unwrap();
    request.abort();
    assert!(request.await.unwrap_err().is_cancelled());
    let mut bytes = Vec::new();
    tokio::time::timeout(
        std::time::Duration::from_secs(2),
        socket.read_to_end(&mut bytes),
    )
    .await
    .unwrap()
    .unwrap();
}

// spec: TUI-RUNTIME-R002.7
#[tokio::test]
async fn bounds_card_bytes_and_removes_terminal_control_characters() {
    let large = "x".repeat(1024 * 1024 + 1);
    let (url, server) = serve("200 OK", &large).await;
    assert_eq!(
        ArboraClient::new(&url, None)
            .unwrap()
            .discover()
            .await
            .unwrap_err(),
        "Arbora Agent Card exceeds size limit"
    );
    server.await.unwrap();
    let (url, server) = serve("200 OK", r#"{"name":"Arb\u001bora\n"}"#).await;
    assert_eq!(
        ArboraClient::new(&url, None)
            .unwrap()
            .discover()
            .await
            .unwrap(),
        "Arbora"
    );
    server.await.unwrap();
}
