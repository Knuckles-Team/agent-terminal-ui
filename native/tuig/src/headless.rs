use std::{io::Write, time::Duration};
use tuig_native::{ArboraClient, TaskSnapshot, TaskSubmission, correlation::TaskState};

fn result(state: TaskState) -> Result<bool, &'static str> {
    match state {
        TaskState::Submitted | TaskState::Working => Ok(false),
        TaskState::Completed => Ok(true),
        TaskState::InputRequired => Err("Task requires input or approval; no approval was sent"),
        TaskState::AuthRequired => Err("Task requires authentication; no credentials were changed"),
        TaskState::Canceled | TaskState::Failed | TaskState::Rejected => {
            Err("Task did not complete successfully")
        }
    }
}

pub async fn run(
    client: &ArboraClient,
    task_id: Option<&str>,
    submission: Option<&TaskSubmission>,
) -> Result<(), &'static str> {
    let observe = async {
        let mut snapshot: TaskSnapshot = match submission {
            Some(submission) => client.submit_task(submission).await?,
            None => {
                client
                    .get_task(task_id.ok_or("Missing task identifier")?)
                    .await?
            }
        };
        let binding = snapshot.correlation.clone();
        let mut previous = String::new();
        loop {
            binding.validate_binding(&snapshot.correlation)?;
            snapshot.terminal_event.validate_binding(&binding)?;
            let display = super::snapshot_status(&snapshot);
            if display != previous {
                let mut output = std::io::stdout().lock();
                writeln!(output, "{display}").map_err(|_| "Cannot write task output")?;
                output.flush().map_err(|_| "Cannot flush task output")?;
                previous = display;
            }
            if result(snapshot.state)? {
                return Ok(());
            }
            tokio::time::sleep(Duration::from_millis(500)).await;
            snapshot = client.refresh_task(&binding).await?;
        }
    };
    tokio::time::timeout(Duration::from_secs(4 * 60 * 60), observe)
        .await
        .map_err(|_| "Observation timed out. No remote task was canceled.")?
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cli::arguments;
    use std::ffi::OsString;

    fn args(values: &[&str]) -> Vec<OsString> {
        values.iter().map(OsString::from).collect()
    }

    // spec: TUIG-RUNTIME-R012.1.3.1
    #[test]
    fn unsupported_flags_and_turn_combinations_are_rejected() {
        for values in [
            vec!["--headless", "--prompt"],
            vec!["--headless", "--prompt", "x", "--override"],
            vec!["--headless", "--prompt", "x", "--bg"],
            vec!["--headless", "--prompt", "x", "--model", "model"],
            vec!["--headless", "--prompt", "x", "--session", "context"],
            vec!["--headless", "--prompt", "x", "--observe-task", "task"],
        ] {
            let (_, remaining) = arguments(&args(&values)).unwrap();
            assert!(super::super::selected_prompt(&remaining, false).is_err());
        }
        let (_, remaining) = arguments(&args(&[
            "--headless",
            "--observe-task",
            "task",
            "--override",
        ]))
        .unwrap();
        assert!(super::super::selected_observation(&remaining, false).is_err());
    }

    // spec: TUIG-RUNTIME-R012.1.3.1
    #[test]
    fn only_completed_is_success_and_approvals_fail_closed() {
        assert_eq!(result(TaskState::Completed), Ok(true));
        assert_eq!(result(TaskState::Submitted), Ok(false));
        assert_eq!(result(TaskState::Working), Ok(false));
        for state in [
            TaskState::InputRequired,
            TaskState::AuthRequired,
            TaskState::Canceled,
            TaskState::Failed,
            TaskState::Rejected,
        ] {
            assert!(result(state).is_err());
        }
    }
}
