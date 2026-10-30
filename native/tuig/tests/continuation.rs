use serde_json::{Value, json};
use std::time::Duration;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
};
use tuig_native::{
    ArboraClient, CONTINUATION_EXTENSION, CONTINUATION_UNAVAILABLE, SUBMISSION_UNKNOWN,
    TaskSubmission,
};

fn context() -> String {
    format!("a2a-context-{}", "a".repeat(64))
}

// spec: TUIG-RUNTIME-R012.3.2.1
#[test]
fn canonical_context_and_fresh_turn_identity() {
    let first = TaskSubmission::continuing("first", &context()).unwrap();
    let second = TaskSubmission::continuing("second", &context()).unwrap();
    assert_ne!(first.message_id(), second.message_id());
    for invalid in [
        String::new(),
        "label".to_owned(),
        context().to_uppercase(),
        format!(" {}", context()),
        format!("{}x", context()),
        format!("a2a-context-{}", "a".repeat(63)),
    ] {
        assert!(TaskSubmission::continuing("text", &invalid).is_err());
    }
    assert!(TaskSubmission::continuing(" ", &context()).is_err());
}

async fn server(
    card: Value,
    reply: Option<(Value, Option<String>)>,
) -> (String, tokio::task::JoinHandle<Vec<String>>) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let endpoint = format!("http://{}", listener.local_addr().unwrap());
    let handle = tokio::spawn(async move {
        let mut responses = vec![(card, None)];
        responses.extend(reply);
        let mut requests = Vec::new();
        for (body, activation) in responses {
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut request = Vec::new();
            loop {
                let mut buffer = [0; 4096];
                let count = socket.read(&mut buffer).await.unwrap();
                assert!(count > 0);
                request.extend_from_slice(&buffer[..count]);
                let text = String::from_utf8_lossy(&request);
                if let Some((headers, body)) = text.split_once("\r\n\r\n") {
                    let length = headers
                        .lines()
                        .find_map(|line| {
                            let (key, value) = line.split_once(':')?;
                            key.eq_ignore_ascii_case("content-length")
                                .then(|| value.trim().parse::<usize>().unwrap())
                        })
                        .unwrap_or(0);
                    if body.len() >= length {
                        break;
                    }
                }
            }
            requests.push(String::from_utf8(request).unwrap());
            let body = body.to_string();
            let activation = activation
                .map(|uri| format!("X-A2A-Extensions: {uri}\r\n"))
                .unwrap_or_default();
            socket.write_all(format!("HTTP/1.1 200 OK\r\nContent-Length: {}\r\n{activation}Connection: close\r\n\r\n{body}", body.len()).as_bytes()).await.unwrap();
        }
        assert!(
            tokio::time::timeout(Duration::from_millis(50), listener.accept())
                .await
                .is_err()
        );
        requests
    });
    (endpoint, handle)
}

fn card() -> Value {
    json!({"capabilities": {"extensions": [{"uri": CONTINUATION_EXTENSION, "required": false}]}})
}

// spec: TUIG-RUNTIME-R012.3.2.1
#[tokio::test]
async fn absent_or_malformed_capability_never_submits() {
    for card in [
        json!({}),
        json!({"capabilities": {"stateTransitionHistory": true}}),
        json!({"capabilities": {"extensions": [{"uri": CONTINUATION_EXTENSION}]}}),
        json!({"capabilities": {"extensions": [{"uri": CONTINUATION_EXTENSION,"required": true}]}}),
        json!({"capabilities": {"extensions": [{"uri": CONTINUATION_EXTENSION,"required": false},{"uri": CONTINUATION_EXTENSION,"required": false}]}}),
    ] {
        let (url, handle) = server(card, None).await;
        let result = ArboraClient::new(&url, Some("token"))
            .unwrap()
            .submit_task(&TaskSubmission::continuing("latest only", &context()).unwrap())
            .await;
        assert_eq!(result.unwrap_err(), CONTINUATION_UNAVAILABLE);
        let requests = handle.await.unwrap();
        assert_eq!(requests.len(), 1);
        assert!(requests[0].starts_with("GET /.well-known/agent-card.json "));
    }
}

// spec: TUIG-RUNTIME-R012.3.2.1
#[tokio::test]
async fn continuation_requires_activation_and_exact_returned_context_without_retry() {
    for (echo, returned, success) in [
        (Some(CONTINUATION_EXTENSION), context(), true),
        (None, context(), false),
        (Some("unknown-extension"), context(), false),
        (
            Some(concat!(
                "https://knuckles-team.github.io/arbora/extensions/completed-text-history/v1",
                "\r\nX-A2A-Extensions: unknown"
            )),
            context(),
            false,
        ),
        (
            Some(CONTINUATION_EXTENSION),
            "context-changed".to_owned(),
            false,
        ),
    ] {
        let submission = TaskSubmission::continuing("latest only", &context()).unwrap();
        let response = json!({"jsonrpc": "2.0", "id": submission.message_id(), "result": {"kind":"task", "id":"task-1", "contextId":returned, "status":{"state":"submitted"}}});
        let (url, handle) = server(card(), Some((response, echo.map(str::to_owned)))).await;
        let result = ArboraClient::new(&url, Some("token"))
            .unwrap()
            .submit_task(&submission)
            .await;
        if success {
            assert_eq!(result.unwrap().correlation.context_id(), context());
        } else {
            assert_eq!(result.unwrap_err(), SUBMISSION_UNKNOWN);
        }
        let requests = handle.await.unwrap();
        assert_eq!(requests.len(), 2);
        let (headers, body) = requests[1].split_once("\r\n\r\n").unwrap();
        assert!(headers.starts_with("POST /a2a "));
        assert!(
            headers
                .to_lowercase()
                .contains(&format!("x-a2a-extensions: {CONTINUATION_EXTENSION}"))
        );
        assert!(
            headers
                .to_lowercase()
                .contains(&format!("idempotency-key: {}", submission.message_id()))
        );
        let value: Value = serde_json::from_str(body).unwrap();
        assert_eq!(value["params"]["message"]["contextId"], context());
        assert_eq!(
            value["params"]["message"]["parts"],
            json!([{"kind":"text", "text":"latest only"}])
        );
        assert_eq!(
            value["params"]["message"]["messageId"],
            submission.message_id()
        );
    }
}
