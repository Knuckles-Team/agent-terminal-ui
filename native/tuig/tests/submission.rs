mod support;

use serde_json::{Value, json};
use std::time::Duration;
use support::{serve, serve_raw};
use tokio::net::TcpListener;
use tuig_native::{ArboraClient, SUBMISSION_UNKNOWN, TaskSubmission, correlation::TaskState};

fn accepted(request_id: &str) -> Value {
    json!({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "kind": "task",
            "id": "task-1",
            "contextId": "context-2",
            "metadata": {"arbora": {"runId": "run-3"}},
            "status": {"state": "submitted"}
        }
    })
}

// spec: TUIG-RUNTIME-R002.1.3.2.2.2.2
#[test]
fn submission_timeout_requires_bounded_whole_seconds() {
    for seconds in [1, 300, 900] {
        assert!(
            ArboraClient::new("http://localhost:1234", Some("token"))
                .unwrap()
                .with_submission_timeout(Duration::from_secs(seconds))
                .is_ok()
        );
    }
    for timeout in [
        Duration::ZERO,
        Duration::from_secs(901),
        Duration::from_millis(1500),
    ] {
        assert!(
            ArboraClient::new("http://localhost:1234", Some("token"))
                .unwrap()
                .with_submission_timeout(timeout)
                .is_err()
        );
    }
}

// spec: TUIG-RUNTIME-R002.1.3.2.2.2.2
#[tokio::test]
async fn submission_default_accepts_a_reply_after_the_read_timeout() {
    let submission = TaskSubmission::new("Queued local fixture").unwrap();
    let body = accepted(submission.message_id()).to_string();
    let response = format!(
        "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let (url, server) = support::serve_raw_after(response, Duration::from_secs(11)).await;
    let result = ArboraClient::new(&url, Some("fixture-token"))
        .unwrap()
        .submit_task(&submission)
        .await
        .unwrap();
    assert_eq!(result.correlation.task_id(), "task-1");
    server.await.unwrap();
}

// spec: TUIG-RUNTIME-R002.1.3.2.2.2.2
#[tokio::test]
async fn submission_timeout_is_unknown_without_resubmission() {
    let submission = TaskSubmission::new("Timeout local fixture").unwrap();
    let body = accepted(submission.message_id()).to_string();
    let response = format!(
        "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let (url, server) = support::serve_raw_after(response, Duration::from_secs(2)).await;
    let result = ArboraClient::new(&url, Some("fixture-token"))
        .unwrap()
        .with_submission_timeout(Duration::from_secs(1))
        .unwrap()
        .submit_task(&submission)
        .await;
    assert_eq!(result.unwrap_err(), SUBMISSION_UNKNOWN);
    server.await.unwrap();
}

// spec: TUIG-RUNTIME-R002.1.3.1
#[tokio::test]
async fn submits_exact_authenticated_text_with_one_stable_identity() {
    for include_run in [true, false] {
        let submission = TaskSubmission::new("Explain this code\nwith café examples").unwrap();
        let identity = submission.message_id().to_owned();
        assert_eq!(identity.len(), 32);
        assert!(identity.bytes().all(|byte| byte.is_ascii_hexdigit()));
        assert_ne!(
            identity,
            TaskSubmission::new("Another turn").unwrap().message_id()
        );
        let mut response = accepted(&identity);
        if !include_run {
            response["result"]
                .as_object_mut()
                .unwrap()
                .remove("metadata");
        }
        let (url, server) = serve("200 OK", &response.to_string()).await;
        let task = ArboraClient::new(&url, Some("fixture-token"))
            .unwrap()
            .submit_task(&submission)
            .await
            .unwrap();
        assert_eq!(submission.message_id(), identity);
        assert_eq!(task.correlation.task_id(), "task-1");
        assert_eq!(task.correlation.context_id(), "context-2");
        assert_eq!(task.correlation.run_id(), include_run.then_some("run-3"));
        assert_eq!(task.state, TaskState::Submitted);
        let request = server.await.unwrap();
        assert!(request.starts_with("POST /a2a HTTP/1.1\r\n"));
        let (headers, body) = request.split_once("\r\n\r\n").unwrap();
        let headers = headers.to_ascii_lowercase();
        assert!(headers.contains("authorization: bearer fixture-token"));
        assert!(headers.contains(&format!("idempotency-key: {identity}\r\n")));
        assert_eq!(
            serde_json::from_str::<Value>(body).unwrap(),
            json!({
                "jsonrpc": "2.0",
                "id": identity,
                "method": "message/send",
                "params": {"configuration": {"blocking": false}, "message": {
                    "kind": "message", "role": "user", "messageId": identity,
                    "parts": [{"kind": "text", "text": "Explain this code\nwith café examples"}]
                }}
            })
        );
    }
}

// spec: TUIG-RUNTIME-R002.1.3.1
#[tokio::test]
async fn invalid_prompt_cannot_create_a_submission_or_send_a_request() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let client =
        ArboraClient::new(&format!("http://{}", listener.local_addr().unwrap()), None).unwrap();
    for prompt in ["", " \n\t", &"x".repeat(65_537), &"é".repeat(32_769)] {
        assert!(TaskSubmission::new(prompt).is_err());
    }
    assert!(TaskSubmission::new(&"x".repeat(65_536)).is_ok());
    assert_eq!(
        client
            .submit_task(&TaskSubmission::new("Valid prompt").unwrap())
            .await
            .unwrap_err(),
        "Submission requires a caller credential"
    );
    assert!(
        tokio::time::timeout(Duration::from_millis(30), listener.accept())
            .await
            .is_err()
    );
}

// spec: TUIG-RUNTIME-R002.1.3.1
#[tokio::test]
async fn malformed_or_refused_submission_never_invents_a_task() {
    let submission = TaskSubmission::new("Read the fixture").unwrap();
    let mut responses = vec![json!(null), json!({}), json!([])];
    for (path, value) in [
        ("/jsonrpc", json!("1.0")),
        ("/id", json!("another-request")),
        ("/id", json!(null)),
        ("/result/id", json!("")),
        ("/result/contextId", json!("")),
        ("/result/kind", json!("message")),
        ("/result/status/state", json!("unknown")),
        ("/result/metadata/arbora/runId", json!(null)),
    ] {
        let mut response = accepted(submission.message_id());
        *response.pointer_mut(path).unwrap() = value;
        responses.push(response);
    }
    let mut response = accepted(submission.message_id());
    response["error"] = json!({"code": -32001, "message": "private-server-detail"});
    responses.push(response);
    let mut response = accepted(submission.message_id());
    response.as_object_mut().unwrap().remove("result");
    responses.push(response);
    for response in responses {
        let (url, server) = serve("200 OK", &response.to_string()).await;
        assert_eq!(
            ArboraClient::new(&url, Some("fixture-token"))
                .unwrap()
                .submit_task(&submission)
                .await
                .unwrap_err(),
            SUBMISSION_UNKNOWN
        );
        server.await.unwrap();
    }
}

// spec: TUIG-RUNTIME-R002.1.3.1
#[tokio::test]
async fn refusal_redirect_invalid_json_and_oversize_remain_unknown_without_retry() {
    let submission = TaskSubmission::new("Read the fixture").unwrap();
    for (status, body) in [
        ("401 Unauthorized", "private-server-detail".to_owned()),
        ("403 Forbidden", "private-server-detail".to_owned()),
        (
            "500 Internal Server Error",
            "private-server-detail".to_owned(),
        ),
        ("302 Found", accepted(submission.message_id()).to_string()),
        ("200 OK", "private-server-detail".to_owned()),
        ("200 OK", "x".repeat(1024 * 1024 + 1)),
    ] {
        let (url, server) = serve(status, &body).await;
        assert_eq!(
            ArboraClient::new(&url, Some("fixture-token"))
                .unwrap()
                .submit_task(&submission)
                .await
                .unwrap_err(),
            SUBMISSION_UNKNOWN
        );
        server.await.unwrap();
    }
}

// spec: TUIG-RUNTIME-R002.1.3.1
// spec: TUIG-RUNTIME-R002.1.3.2.2.2.2
#[tokio::test]
async fn lost_or_interrupted_submission_response_has_no_automatic_resend() {
    let submission = TaskSubmission::new("Read the fixture").unwrap();
    for response in ["", "HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n{"] {
        let (url, server) = serve_raw(response.to_owned()).await;
        assert_eq!(
            ArboraClient::new(&url, Some("fixture-token"))
                .unwrap()
                .submit_task(&submission)
                .await
                .unwrap_err(),
            SUBMISSION_UNKNOWN
        );
        server.await.unwrap();
    }
}
