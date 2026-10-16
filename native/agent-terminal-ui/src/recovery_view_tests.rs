use super::*;
use ratatui::{Terminal, backend::TestBackend};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
};

// spec: TUI-RUNTIME-R002.1.3.2.1
#[tokio::test]
async fn http_denial_clears_rendered_snapshot_and_disarms_cancel_until_refresh() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let client = GraphOsClient::new(
        &format!("http://{}", listener.local_addr().unwrap()),
        Some("fixture-token"),
    )
    .unwrap();
    let server = tokio::spawn(async move {
        for status in [200, 403, 200] {
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
                    if body.len() < length {
                        continue;
                    }
                    let payload: serde_json::Value = serde_json::from_str(body).unwrap();
                    assert_eq!(payload["method"], "tasks/get");
                    break;
                }
            }
            let body = serde_json::json!({"jsonrpc":"2.0", "id":"task-snapshot", "result":{
                "kind":"task", "id":"task-one", "contextId":"context-two",
                "metadata":{"graphOs":{"runId":"run-three"}}, "status":{"state":"working"}
            }})
            .to_string();
            socket.write_all(format!("HTTP/1.1 {status} Fixture\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len()).as_bytes()).await.unwrap();
        }
    });
    let mut binding = None;
    let mut cancellation = Cancellation::default();
    let mut terminal = Terminal::new(TestBackend::new(160, 20)).unwrap();
    for denied in [false, true, false] {
        let result = read_status(&client, Some("task-one"), binding.as_ref()).await;
        let status = request_completed(Ok(result), &mut binding, &mut cancellation, false);
        terminal
            .draw(|frame| draw(frame, &status, Style::default()))
            .unwrap();
        let text: String = terminal
            .backend()
            .buffer()
            .content()
            .iter()
            .map(|cell| cell.symbol())
            .collect();
        for protected in ["task-one", "context-two", "run-three", "State: working"] {
            assert_eq!(text.contains(protected), !denied);
        }
        if denied {
            assert!(text.contains("GraphOS task read refused or unavailable"));
            cancellation.arm();
            assert!(!cancellation.confirm());
            assert_eq!(cancellation, Cancellation::Unavailable);
        } else {
            assert_eq!(cancellation, Cancellation::Ready);
        }
        assert_eq!(binding.as_ref().unwrap().run_id(), Some("run-three"));
    }
    server.await.unwrap();
}
