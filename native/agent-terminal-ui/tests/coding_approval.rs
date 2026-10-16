use agent_terminal_ui_native::coding_approval::*;
use ratatui::{Terminal, backend::TestBackend};

fn request() -> ApprovalRequest {
    ApprovalRequest {
        session_id: "session-a".into(),
        request_id: "write-a".into(),
        workspace_root: "/workspace".into(),
        content: RequestContent::Write {
            resolved_path: "/workspace/file".into(),
            old_text: "old-secret\n".into(),
            new_text: "new-secret".into(),
        },
    }
}
fn state() -> CodingApprovalState {
    let mut state = CodingApprovalState::new(
        "session-a".into(),
        "/workspace".into(),
        [Capability::WriteText, Capability::CreateTerminal]
            .into_iter()
            .collect(),
    );
    state.set_connected(true);
    state
}
// spec: TUI-RUNTIME-R011.1
#[test]
fn capability_set_is_closed() {
    for method in [
        "fs/read_text_file",
        "fs/write_text_file",
        "terminal/create",
        "terminal/output",
        "terminal/wait_for_exit",
        "terminal/kill",
    ] {
        assert_eq!(Capability::parse(method).unwrap().method(), method);
    }
    assert_eq!(
        Capability::parse("shell/execute"),
        Err(ApprovalError::CapabilityNotGranted)
    );
    let mut state =
        CodingApprovalState::new("session-a".into(), "/workspace".into(), Default::default());
    state.set_connected(true);
    assert_eq!(
        state.receive(request()),
        Err(ApprovalError::CapabilityNotGranted)
    );
}
// spec: TUI-RUNTIME-R011.4
#[test]
fn diff_precedes_explicit_choice_and_preserves_missing_newline() {
    let mut state = state();
    state.receive(request()).unwrap();
    assert!(state.records().is_empty());
    let preview = state.preview().unwrap();
    let mut terminal = Terminal::new(TestBackend::new(110, 18)).unwrap();
    terminal.draw(|f| preview.render(f, f.area())).unwrap();
    let buffer: String = terminal
        .backend()
        .buffer()
        .content
        .iter()
        .map(|cell| cell.symbol())
        .collect();
    for text in [
        "--- before",
        "+++ after",
        "@@ -1,1 +1,1 @@",
        "-old-secret",
        "+new-secret",
        "No newline at end of file",
        "Explicit approve or deny",
    ] {
        assert!(buffer.contains(text), "{text}");
    }
    let record = state.decide(&preview, Choice::Approve, "operator").unwrap();
    assert_eq!(record.choice, Choice::Approve);
    assert!(state.preview().is_none());
    assert_eq!(
        state.decide(&preview, Choice::Approve, "operator"),
        Err(ApprovalError::RequestChanged)
    );
    assert_eq!(
        state.receive(request()),
        Err(ApprovalError::AlreadyAnswered)
    );
}
// spec: TUI-RUNTIME-R011.4, TUI-RUNTIME-R011.5, TUI-RUNTIME-R011.11
#[test]
fn denied_write_and_command_produce_only_metadata() {
    let mut command = request();
    command.request_id = "command-a".into();
    command.content = RequestContent::Command {
        command: "echo secret-command".into(),
        working_directory: "/workspace".into(),
        danger: "high".into(),
        command_digest: "adapter-bound-digest".into(),
    };
    for request in [request(), command] {
        let mut state = state();
        state.receive(request.clone()).unwrap();
        let preview = state.preview().unwrap();
        if matches!(request.content, RequestContent::Command { .. }) {
            let text = preview.text();
            for field in [
                "Command: echo secret-command",
                "Working directory: /workspace",
                "Danger: high",
            ] {
                assert!(text.contains(field));
            }
        }
        let record = state.decide(&preview, Choice::Deny, "operator").unwrap();
        assert_eq!(record.choice, Choice::Deny);
        assert_eq!(state.records(), std::slice::from_ref(&record));
        let evidence = format!("{record:?}\n{}", record.text());
        for secret in ["old-secret", "new-secret", "echo secret-command"] {
            assert!(!evidence.contains(secret));
        }
        assert!(evidence.contains("operator"));
        assert!(state.preview().is_none());
    }
}
// spec: TUI-RUNTIME-R011.7
#[test]
fn disconnect_and_reattach_retain_unanswered_request() {
    let mut state = state();
    state.receive(request()).unwrap();
    let preview = state.preview().unwrap();
    state.set_connected(false);
    assert_eq!(state.preview().unwrap().text(), preview.text());
    assert_eq!(
        state.decide(&preview, Choice::Approve, "operator"),
        Err(ApprovalError::GatewayUnavailable)
    );
    assert_eq!(
        state.receive(request()),
        Err(ApprovalError::GatewayUnavailable)
    );
    state.set_connected(true);
    state.receive(request()).unwrap();
    assert_eq!(state.preview().unwrap().text(), preview.text());
    assert!(state.records().is_empty());
    state
        .decide(&state.preview().unwrap(), Choice::Deny, "operator")
        .unwrap();
}
// spec: TUI-RUNTIME-R011.4, TUI-RUNTIME-R011.5
#[test]
fn changed_foreign_and_other_pending_requests_cannot_reuse_preview() {
    let mut state = state();
    state.receive(request()).unwrap();
    let original = state.preview().unwrap().text();
    for change in 0..4 {
        let mut changed = request();
        match change {
            0 => changed.session_id = "other-session".into(),
            1 => changed.workspace_root = "/other".into(),
            2 => changed.request_id = "other-request".into(),
            _ => {
                changed.content = RequestContent::Write {
                    resolved_path: "/workspace/file".into(),
                    old_text: "changed".into(),
                    new_text: "new-secret".into(),
                }
            }
        }
        assert!(state.receive(changed.clone()).is_err());
        assert_eq!(state.preview().unwrap().text(), original);
        let mut foreign = CodingApprovalState::new(
            changed.session_id.clone(),
            changed.workspace_root.clone(),
            [Capability::WriteText].into_iter().collect(),
        );
        foreign.set_connected(true);
        foreign.receive(changed).unwrap();
        assert_eq!(
            state.decide(&foreign.preview().unwrap(), Choice::Approve, "operator"),
            Err(ApprovalError::RequestChanged)
        );
    }
    assert!(state.records().is_empty());
}
// spec: TUI-RUNTIME-R011.4, TUI-RUNTIME-R011.11
#[test]
fn preview_escapes_terminal_controls_and_rejects_missing_actor() {
    let mut state = state();
    let mut request = request();
    request.content = RequestContent::Write {
        resolved_path: "/workspace/file".into(),
        old_text: String::new(),
        new_text: "\x1b[2J\n".into(),
    };
    state.receive(request).unwrap();
    let preview = state.preview().unwrap();
    assert!(!preview.text().contains('\x1b'));
    assert!(preview.text().contains("@@ -0,0 +1,1 @@"));
    assert_eq!(
        state.decide(&preview, Choice::Deny, " "),
        Err(ApprovalError::InvalidMetadata)
    );
    assert!(state.preview().is_some());
}

// spec: TUI-RUNTIME-R011.5
#[test]
fn command_choice_binds_every_preview_field() {
    let mut original = request();
    original.content = RequestContent::Command {
        command: "echo original".into(),
        working_directory: "/workspace".into(),
        danger: "low".into(),
        command_digest: "original-digest".into(),
    };
    let mut state = state();
    state.receive(original.clone()).unwrap();
    for field in 0..4 {
        let mut changed = original.clone();
        if let RequestContent::Command {
            command,
            working_directory,
            danger,
            command_digest,
        } = &mut changed.content
        {
            match field {
                0 => *command = "echo changed".into(),
                1 => *working_directory = "/elsewhere".into(),
                2 => *danger = "high".into(),
                _ => *command_digest = "changed-digest".into(),
            }
        }
        assert_eq!(
            state.receive(changed.clone()),
            Err(ApprovalError::RequestChanged)
        );
        let mut other = CodingApprovalState::new(
            "session-a".into(),
            "/workspace".into(),
            [Capability::CreateTerminal].into_iter().collect(),
        );
        other.set_connected(true);
        other.receive(changed).unwrap();
        assert_eq!(
            state.decide(&other.preview().unwrap(), Choice::Approve, "operator"),
            Err(ApprovalError::RequestChanged)
        );
    }
    assert!(state.records().is_empty());
    assert!(state.preview().unwrap().text().contains("echo original"));
}
