use std::process::{Command, Output};

fn invoke(args: &[&str], invalid_configuration: bool) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_tuig"));
    command.args(args).env_clear();
    if invalid_configuration {
        command
            .env("AGENT_URL", "invalid endpoint")
            .env("AGENT_AUTH_MODE", "invalid mode")
            .env("AGENT_TASK_ID", "")
            .env("AGENT_SUBMISSION_TIMEOUT_SECONDS", "invalid timeout");
    }
    command.output().expect("native CLI must execute")
}

// spec: TUIG-RUNTIME-R015.30.2
#[test]
fn help_is_available_without_runtime_configuration_or_a_terminal() {
    for invalid_configuration in [false, true] {
        let long = invoke(&["--help"], invalid_configuration);
        let short = invoke(&["-h"], invalid_configuration);
        assert!(long.status.success());
        assert!(short.status.success());
        assert_eq!(long.stdout, short.stdout);
        assert!(long.stderr.is_empty());
        assert!(short.stderr.is_empty());
        let help = String::from_utf8(long.stdout).unwrap();
        for text in [
            "Tuig: native Arbora terminal",
            "Usage: tuig",
            "--prompt TEXT",
            "--observe-task TASK_ID",
            "-h, --help",
            "AGENT_URL",
            "AGENT_BEARER_TOKEN",
            "AGENT_AUTH_MODE",
            "AGENT_TASK_ID",
            "AGENT_SUBMISSION_TIMEOUT_SECONDS",
            "AGENT_INCLUDE_COMMITTED_EVENT",
            "AGENT_THEME",
            "NO_COLOR",
            "cannot be combined",
            "does not resume chat",
            "Central task streaming and approvals remain unavailable",
        ] {
            assert!(help.contains(text), "missing help: {text}");
        }
    }
}

// spec: TUIG-RUNTIME-R015.30.2
#[test]
fn help_does_not_swallow_values_or_invalid_argument_combinations() {
    for args in [
        vec!["--help", "--prompt", "task"],
        vec!["--observe-task", "task", "--help"],
        vec!["--help", "extra"],
        vec!["-h", "--help"],
    ] {
        let result = invoke(&args, false);
        assert!(!result.status.success(), "accepted {args:?}");
        assert!(result.stdout.is_empty());
        assert!(!result.stderr.is_empty());
    }
    let prompt = invoke(&["--prompt", "--help"], false);
    assert!(!prompt.status.success());
    assert!(prompt.stdout.is_empty());
    assert_eq!(
        String::from_utf8(prompt.stderr).unwrap().trim(),
        "Submission requires a caller credential"
    );
}
