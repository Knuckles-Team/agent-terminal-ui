#[cfg(unix)]
use agent_terminal_ui_native::acp::{TextClient, completed};
use std::ffi::OsString;
#[cfg(unix)]
use std::{path::PathBuf, process::Stdio, time::Duration};
#[cfg(unix)]
use tokio::{process::Command, time::timeout};

pub struct Options {
    pub model: String,
    pub prompt: String,
}

pub fn options(args: &[OsString]) -> Result<Option<Options>, &'static str> {
    let mut local = false;
    let mut headless = false;
    let mut model = None;
    let mut prompt = None;
    let mut other = false;
    let mut index = 0;
    while index < args.len() {
        match args[index].to_str() {
            Some("--local-runtime") if !local => local = true,
            Some("--headless") if !headless => headless = true,
            Some("--local-model") | Some("--prompt") => {
                let flag = args[index].to_str();
                index += 1;
                let value = args.get(index).and_then(|arg| arg.to_str());
                let target = if flag == Some("--local-model") {
                    &mut model
                } else {
                    &mut prompt
                };
                if target.is_some() || value.is_none() {
                    other = true;
                }
                *target = value.map(str::to_owned);
            }
            Some("--observe-task") => {
                other = true;
                index += 1;
            }
            _ => other = true,
        }
        index += 1;
    }
    if !local {
        return Ok(None);
    }
    if other || !headless {
        return Err(
            "Local runtime requires --headless --local-model PROVIDER:MODEL --prompt TEXT only",
        );
    }
    let model = model
        .filter(|value| {
            value.len() <= 512
                && !value.chars().any(char::is_whitespace)
                && value
                    .split_once(':')
                    .is_some_and(|(provider, name)| !provider.is_empty() && !name.is_empty())
                && !value.starts_with('-')
        })
        .ok_or("Local runtime requires --local-model PROVIDER:MODEL")?;
    let prompt = prompt
        .filter(|value| !value.trim().is_empty() && value.len() <= 16_384)
        .ok_or("Local runtime requires --prompt TEXT (1..16384 bytes)")?;
    Ok(Some(Options { model, prompt }))
}

#[cfg(unix)]
struct Output {
    stdout: std::io::Stdout,
    flags: rustix::fs::OFlags,
}

#[cfg(unix)]
impl Output {
    fn new() -> Result<Self, &'static str> {
        let stdout = std::io::stdout();
        let flags = rustix::fs::fcntl_getfl(&stdout).map_err(|_| "Cannot inspect ACP output")?;
        rustix::fs::fcntl_setfl(&stdout, flags | rustix::fs::OFlags::NONBLOCK)
            .map_err(|_| "Cannot make ACP output cancelable")?;
        Ok(Self { stdout, flags })
    }

    async fn write(&self, text: &str) -> Result<(), &'static str> {
        let safe: String = text
            .chars()
            .filter(|c| !c.is_control() || matches!(c, '\n' | '\t'))
            .collect();
        let mut remaining = safe.as_bytes();
        while !remaining.is_empty() {
            match rustix::io::write(&self.stdout, remaining) {
                Ok(0) => return Err("ACP output closed"),
                Ok(count) => remaining = &remaining[count..],
                Err(rustix::io::Errno::AGAIN | rustix::io::Errno::INTR) => {
                    tokio::time::sleep(Duration::from_millis(10)).await;
                }
                Err(_) => return Err("Cannot write ACP output"),
            }
        }
        Ok(())
    }
}

#[cfg(unix)]
impl Drop for Output {
    fn drop(&mut self) {
        // Restore the inherited file description even after a canceled write.
        let _ = rustix::fs::fcntl_setfl(&self.stdout, self.flags);
    }
}

#[cfg(not(unix))]
pub async fn run(_options: Options) -> Result<(), &'static str> {
    Err("Local ACP runtime currently requires a POSIX host")
}

#[cfg(unix)]
fn backend_executable() -> Result<PathBuf, &'static str> {
    let executable = std::env::current_exe()
        .and_then(std::fs::canonicalize)
        .map_err(|_| "Cannot resolve installed tuig executable")?;
    let candidate = executable
        .parent()
        .ok_or("Cannot resolve installed tuig directory")?
        .join("arbora-acp");
    match std::fs::symlink_metadata(&candidate) {
        Ok(_) => Ok(candidate),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            Ok(PathBuf::from("arbora-acp"))
        }
        Err(_) => Err("Cannot inspect installed Arbora local runtime"),
    }
}

#[cfg(unix)]
pub async fn run(options: Options) -> Result<(), &'static str> {
    if std::env::var_os("AGENT_TASK_ID").is_some() {
        return Err("Local runtime cannot be combined with AGENT_TASK_ID");
    }
    let output = Output::new()?;
    let root = std::env::current_dir()
        .and_then(std::fs::canonicalize)
        .map_err(|_| "Cannot resolve local workspace")?;
    let cwd = root
        .to_str()
        .ok_or("Local workspace must be valid Unicode")?;
    let mut child = Command::new(backend_executable()?)
        .args([
            "--local",
            "--model",
            &options.model,
            "--workspace-root",
            cwd,
        ])
        .current_dir(&root)
        .env_remove("AGENT_BEARER_TOKEN")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .kill_on_drop(true)
        .spawn()
        .map_err(|_| "Cannot start arbora-acp; install the compatible Arbora local runtime")?;
    let stdout = child.stdout.take().ok_or("Missing ACP output pipe")?;
    let stdin = child.stdin.take().ok_or("Missing ACP input pipe")?;
    let mut client = TextClient::new(stdout, stdin);
    let exchange = async {
        timeout(Duration::from_secs(30), client.initialize(cwd))
            .await
            .map_err(|_| "Local ACP initialization timed out")??;
        client.prompt(&options.prompt).await?;
        client
            .response(3, async |text| output.write(text).await)
            .await
    };
    let result = tokio::select! {
        biased;
        _ = tokio::signal::ctrl_c() => Err("Local ACP interrupted; cancellation requested"),
        result = timeout(Duration::from_secs(330), exchange) => {
            result.unwrap_or(Err("Local ACP turn timed out; cancellation requested"))
        }
    };
    let turn = match result {
        Ok(value) => completed(&value),
        Err(error) => {
            // A cancel notification is not an acknowledgement. Drain briefly, then reap.
            let _ = timeout(Duration::from_secs(5), async {
                client.cancel().await?;
                client.response(3, async |_| Ok(())).await
            })
            .await;
            Err(error)
        }
    };
    let closed = timeout(Duration::from_secs(2), client.close())
        .await
        .unwrap_or(Err("Local ACP close timed out"));
    drop(client);
    let status = match timeout(Duration::from_secs(2), child.wait()).await {
        Ok(result) => result.map_err(|_| "Cannot reap owned ACP backend")?,
        Err(_) => {
            child
                .kill()
                .await
                .map_err(|_| "Cannot stop owned ACP backend")?;
            child
                .wait()
                .await
                .map_err(|_| "Cannot reap owned ACP backend")?
        }
    };
    if turn.is_ok() && !status.success() {
        return Err("Owned ACP backend did not exit successfully");
    }
    turn.and(closed)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn args(values: &[&str]) -> Vec<OsString> {
        values.iter().map(OsString::from).collect()
    }

    // spec: TUI-RUNTIME-R011.14
    #[test]
    fn explicit_local_mode_does_not_capture_prompt_data_or_central_mode() {
        assert!(
            options(&args(&["--prompt", "--local-runtime"]))
                .unwrap()
                .is_none()
        );
        assert!(
            options(&args(&["--headless", "--prompt", "text"]))
                .unwrap()
                .is_none()
        );
        assert!(
            options(&args(&["--observe-task", "--local-runtime"]))
                .unwrap()
                .is_none()
        );
        let parsed = options(&args(&[
            "--local-runtime",
            "--headless",
            "--local-model",
            "test:model",
            "--prompt",
            "--headless",
        ]))
        .unwrap()
        .unwrap();
        assert_eq!(parsed.prompt, "--headless");
        assert_eq!(parsed.model, "test:model");
        for values in [
            vec!["--local-runtime"],
            vec![
                "--local-runtime",
                "--headless",
                "--local-model",
                "test:model",
                "--prompt",
                "x",
                "--override",
            ],
            vec![
                "--local-runtime",
                "--headless",
                "--local-model",
                "test:model",
                "--prompt",
                "x",
                "--observe-task",
                "task",
            ],
            vec![
                "--local-runtime",
                "--headless",
                "--local-model",
                "bad",
                "--prompt",
                "x",
            ],
            vec![
                "--local-runtime",
                "--headless",
                "--local-model",
                "test:model",
                "--prompt",
                "x",
                "--local-runtime",
            ],
        ] {
            assert!(options(&args(&values)).is_err());
        }
    }
}
