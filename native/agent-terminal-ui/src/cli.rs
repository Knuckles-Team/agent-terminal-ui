use std::ffi::OsString;

pub fn arguments(args: &[OsString]) -> Result<(bool, Vec<OsString>), &'static str> {
    let mut headless = false;
    let mut remaining = Vec::new();
    let mut index = 0;
    while index < args.len() {
        if args[index] == "--headless" {
            if headless {
                return Err("--headless may be supplied only once");
            }
            headless = true;
        } else {
            remaining.push(args[index].clone());
            // A prompt or identifier is data, even when it looks like a flag.
            if args[index] == "--prompt"
                || args[index] == "--observe-task"
                || args[index] == "--continue"
            {
                index += 1;
                if let Some(value) = args.get(index) {
                    remaining.push(value.clone());
                }
            }
        }
        index += 1;
    }
    if headless && remaining.is_empty() {
        return Err("--headless requires --prompt TEXT or --observe-task TASK_ID");
    }
    Ok((headless, remaining))
}

pub fn continuation(
    args: &[OsString],
    task_selected: bool,
) -> Result<(Option<String>, Vec<OsString>), &'static str> {
    let mut context = None;
    let mut remaining = Vec::new();
    let mut index = 0;
    while index < args.len() {
        if args[index] == "--continue" {
            if context.is_some() || task_selected {
                return Err("--continue cannot be repeated or combined with AGENT_TASK_ID");
            }
            index += 1;
            let value = args
                .get(index)
                .and_then(|value| value.to_str())
                .ok_or("--continue requires a context identifier")?;
            agent_terminal_ui_native::validate_context_id(value)?;
            context = Some(value.to_owned());
        } else {
            remaining.push(args[index].clone());
            if args[index] == "--prompt" || args[index] == "--observe-task" {
                index += 1;
                if let Some(value) = args.get(index) {
                    remaining.push(value.clone());
                }
            }
        }
        index += 1;
    }
    if context.is_some() && !matches!(remaining.as_slice(), [flag, _] if flag == "--prompt") {
        return Err("--continue requires exactly --prompt TEXT and cannot observe a task");
    }
    Ok((context, remaining))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn args(values: &[&str]) -> Vec<OsString> {
        values.iter().map(OsString::from).collect()
    }

    // spec: TUI-RUNTIME-R012.1.3.1
    #[test]
    fn headless_is_explicit_and_preserves_argument_data() {
        for values in [
            vec!["--headless", "--prompt", "hello"],
            vec!["--prompt", "hello", "--headless"],
        ] {
            assert_eq!(
                arguments(&args(&values)),
                Ok((true, args(&["--prompt", "hello"])))
            );
        }
        assert_eq!(
            arguments(&args(&["--prompt", "--headless"])),
            Ok((false, args(&["--prompt", "--headless"])))
        );
        assert!(arguments(&args(&["--headless"])).is_err());
        assert!(arguments(&args(&["--headless", "--headless", "--prompt", "x"])).is_err());
    }
}

#[cfg(test)]
mod continuation_tests {
    use super::*;

    fn args(values: &[&str]) -> Vec<OsString> {
        values.iter().map(OsString::from).collect()
    }

    // spec: TUI-RUNTIME-R012.3.2.1
    #[test]
    fn continuation_requires_one_canonical_context_and_new_prompt() {
        let context = format!("a2a-context-{}", "a".repeat(64));
        for input in [
            vec!["--continue", &context, "--prompt", "new text"],
            vec!["--prompt", "new text", "--continue", &context],
        ] {
            assert_eq!(
                continuation(&args(&input), false),
                Ok((Some(context.clone()), args(&["--prompt", "new text"])))
            );
            assert!(continuation(&args(&input), true).is_err());
        }
        for input in [
            vec!["--continue"],
            vec!["--continue", &context],
            vec!["--continue", "label", "--prompt", "text"],
            vec![
                "--continue",
                &context,
                "--continue",
                &context,
                "--prompt",
                "text",
            ],
            vec!["--continue", &context, "--observe-task", "task"],
            vec![
                "--continue",
                &context,
                "--prompt",
                "text",
                "--prompt",
                "again",
            ],
        ] {
            assert!(continuation(&args(&input), false).is_err());
        }
        assert_eq!(
            continuation(&args(&["--prompt", "--continue"]), false),
            Ok((None, args(&["--prompt", "--continue"])))
        );
        assert!(
            super::super::local_runtime::options(&args(&[
                "--local-runtime",
                "--local-model",
                "test:model",
                "--continue",
                &context,
                "--prompt",
                "text"
            ]))
            .is_err()
        );
        assert_eq!(
            arguments(&args(&["--continue", "--headless"])),
            Ok((false, args(&["--continue", "--headless"])))
        );
    }
}
