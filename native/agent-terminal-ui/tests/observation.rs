use std::{io::ErrorKind, net::TcpListener, process::Command};

#[test]
fn invalid_observation_arguments_and_missing_credentials_make_zero_requests() {
    for (args, credential, task_env) in [
        (vec!["--observe-task", "task-1"], false, None),
        (vec!["--observe-task", ""], true, None),
        (vec!["--observe-task", "task-1", "--override"], true, None),
        (
            vec!["--observe-task", "task-1", "--prompt", "effect"],
            true,
            None,
        ),
        (vec!["--observe-task", "task-1"], true, Some("other-task")),
    ] {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let mut command = Command::new(env!("CARGO_BIN_EXE_agent-terminal-ui-native"));
        command
            .args(args)
            .env(
                "AGENT_URL",
                format!("http://{}", listener.local_addr().unwrap()),
            )
            .env_remove("AGENT_TASK_ID")
            .env_remove("AGENT_BEARER_TOKEN");
        if credential {
            command.env("AGENT_BEARER_TOKEN", "fixture-token");
        }
        if let Some(task) = task_env {
            command.env("AGENT_TASK_ID", task);
        }
        let output = command.output().unwrap();
        assert!(!output.status.success());
        assert!(output.stdout.is_empty());
        assert_eq!(listener.accept().unwrap_err().kind(), ErrorKind::WouldBlock);
    }
}
