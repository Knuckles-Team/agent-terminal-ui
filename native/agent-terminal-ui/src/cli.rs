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
            if args[index] == "--prompt" || args[index] == "--observe-task" {
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
