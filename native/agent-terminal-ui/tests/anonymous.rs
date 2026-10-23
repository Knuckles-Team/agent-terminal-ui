mod support;

use agent_terminal_ui_native::{ArboraClient, AuthMode, TaskSubmission};
use serde_json::{Value, json};

fn task(id: &str, state: &str) -> Value {
    json!({"jsonrpc":"2.0", "id":id, "result": {
        "kind":"task", "id":"task-1", "contextId":"context-1",
        "status":{"state":state}
    }})
}

// spec: TUI-RUNTIME-R002.1.3.3
#[test]
fn anonymous_mode_is_explicit_and_loopback_only() {
    assert_eq!(AuthMode::parse(None), Ok(AuthMode::Bearer));
    assert_eq!(AuthMode::parse(Some("bearer")), Ok(AuthMode::Bearer));
    assert_eq!(AuthMode::parse(Some("none")), Ok(AuthMode::None));
    for invalid in ["", "None", "anonymous", " none", "none "] {
        assert!(AuthMode::parse(Some(invalid)).is_err());
    }
    for endpoint in [
        "http://example.com",
        "https://example.com",
        "http://0.0.0.0",
        "http://localhost.example.com",
        "http://user@localhost",
        "http://localhost/path",
    ] {
        assert!(ArboraClient::with_auth_mode(endpoint, None, AuthMode::None).is_err());
    }
    for endpoint in ["http://127.0.0.1", "http://localhost", "http://[::1]"] {
        assert!(ArboraClient::with_auth_mode(endpoint, None, AuthMode::None).is_ok());
        for token in ["", "fixture-token"] {
            assert!(ArboraClient::with_auth_mode(endpoint, Some(token), AuthMode::None).is_err());
        }
    }
}

// spec: TUI-RUNTIME-R002.1.3.3
#[tokio::test]
async fn anonymous_submit_read_and_cancel_never_send_authorization() {
    let submission = TaskSubmission::new("Local anonymous task").unwrap();
    let (url, server) = support::serve(
        "200 OK",
        &task(submission.message_id(), "submitted").to_string(),
    )
    .await;
    let snapshot = ArboraClient::with_auth_mode(&url, None, AuthMode::None)
        .unwrap()
        .submit_task(&submission)
        .await
        .unwrap();
    let request = server.await.unwrap();
    assert!(!request.to_lowercase().contains("authorization:"));
    assert!(request.contains("message/send"));
    let (url, server) =
        support::serve("200 OK", &task("task-snapshot", "working").to_string()).await;
    let url = url.replace("127.0.0.1", "localhost");
    let read = ArboraClient::with_auth_mode(&url, None, AuthMode::None)
        .unwrap()
        .get_task("task-1")
        .await
        .unwrap();
    snapshot
        .correlation
        .validate_binding(&read.correlation)
        .unwrap();
    let request = server.await.unwrap();
    assert!(!request.to_lowercase().contains("authorization:"));
    assert!(request.contains("tasks/get"));
    let (url, server) =
        support::serve("200 OK", &task("task-cancel", "canceled").to_string()).await;
    ArboraClient::with_auth_mode(&url, None, AuthMode::None)
        .unwrap()
        .cancel_task(&snapshot.correlation)
        .await
        .unwrap();
    let request = server.await.unwrap();
    assert!(!request.to_lowercase().contains("authorization:"));
    assert!(request.contains("tasks/cancel"));
}

// spec: TUI-RUNTIME-R002.1.3.3
#[tokio::test]
async fn neither_mode_retries_refusal_or_follows_redirects() {
    for mode in [AuthMode::None, AuthMode::Bearer] {
        for status in ["401 Unauthorized", "403 Forbidden", "302 Found"] {
            let (url, server) = support::serve(status, "protected detail").await;
            let token = (mode == AuthMode::Bearer).then_some("fixture-token");
            assert!(
                ArboraClient::with_auth_mode(&url, token, mode)
                    .unwrap()
                    .submit_task(&TaskSubmission::new("One attempt").unwrap())
                    .await
                    .is_err()
            );
            let request = server.await.unwrap();
            assert_eq!(
                request.to_lowercase().contains("authorization:"),
                mode == AuthMode::Bearer
            );
        }
    }
}

// spec: TUI-RUNTIME-R002.1.3.3
#[tokio::test]
async fn anonymous_tasks_do_not_grant_authenticated_host_log_authority() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    let client = ArboraClient::with_auth_mode(&url, None, AuthMode::None).unwrap();
    assert!(
        agent_terminal_ui_native::host_logs::HostLogs::bind(std::sync::Arc::new(client))
            .await
            .is_err()
    );
    assert!(
        tokio::time::timeout(std::time::Duration::from_millis(30), listener.accept())
            .await
            .is_err()
    );
}
