use agent_terminal_ui_native::{
    ArboraClient, SUBMISSION_UNKNOWN, TaskSnapshot, TaskSubmission,
    correlation::{TaskCorrelation, TaskState},
};
use crossterm::event::{Event, EventStream, KeyCode, KeyEventKind, KeyModifiers};
use futures_util::StreamExt;
use ratatui::{
    Frame,
    style::Style,
    widgets::{Block, Paragraph, Wrap},
};
use std::{env, ffi::OsString, process::ExitCode, sync::Arc};

mod host_log_view;
mod inspector_view;
use host_log_view::HostLogView;
mod presentation;
use inspector_view::InspectorView;
use presentation::{Viewport, presentation_style};

#[cfg(test)]
fn draw(frame: &mut Frame, status: &str, style: Style) {
    draw_viewport(frame, status, style, &mut Viewport::default(), false);
}

fn draw_viewport(
    frame: &mut Frame,
    status: &str,
    style: Style,
    viewport: &mut Viewport,
    read_only: bool,
) {
    let cancel_help = if read_only {
        "read-only observation"
    } else {
        "x: cancel remote task"
    };
    let text = format!(
        "{status}\n\nTask streaming and approvals remain unavailable.\n\nl: host logs | i: run inspector | r: refresh read | {cancel_help} | c: cancel local request | q / Ctrl+C: quit"
    );
    let block = Block::bordered()
        .title("Arbora")
        .title_bottom("PgUp/PgDn Home/End");
    let inner = block.inner(frame.area());
    let paragraph = Paragraph::new(text).style(style).wrap(Wrap { trim: false });
    viewport.measure(paragraph.line_count(inner.width), inner.height);
    frame.render_widget(
        paragraph.scroll((viewport.offset(), 0)).block(block),
        frame.area(),
    );
}

fn draw_confirmation(frame: &mut Frame, status: &str, style: Style) -> bool {
    let fits = frame.area().width >= 34 && frame.area().height >= 5;
    let text = if fits {
        format!("Cancel selected remote task?\ny: confirm | n / Escape: dismiss\n\n{status}")
    } else {
        "Resize to confirm. n / Escape: dismiss".to_owned()
    };
    frame.render_widget(
        Paragraph::new(text)
            .style(style)
            .wrap(Wrap { trim: false })
            .block(Block::bordered().title("Confirm cancellation")),
        frame.area(),
    );
    fits
}

fn confirm_visible(
    cancellation: &mut Cancellation,
    visible: bool,
    size: std::io::Result<(u16, u16)>,
) -> bool {
    visible
        && matches!(size, Ok((width, height)) if width >= 34 && height >= 5)
        && cancellation.confirm()
}

fn selected_task(value: Result<String, env::VarError>) -> Result<Option<String>, &'static str> {
    match value {
        Ok(task)
            if task.trim().is_empty() || task.len() > 512 || task.chars().any(char::is_control) =>
        {
            Err("AGENT_TASK_ID must be a non-empty task identifier")
        }
        Ok(task) => Ok(Some(task)),
        Err(env::VarError::NotPresent) => Ok(None),
        Err(env::VarError::NotUnicode(_)) => Err("AGENT_TASK_ID must be valid Unicode"),
    }
}

fn selected_prompt(args: &[OsString], task_selected: bool) -> Result<Option<String>, &'static str> {
    if args.is_empty() {
        return Ok(None);
    }
    let [flag, prompt] = args else {
        return Err("Expected exactly --prompt TEXT, or no arguments");
    };
    if flag != "--prompt" {
        return Err("Unknown argument; expected --prompt TEXT");
    }
    if task_selected {
        return Err("--prompt cannot be combined with AGENT_TASK_ID");
    }
    let prompt = prompt.to_str().ok_or("Prompt must be valid Unicode")?;
    if prompt.trim().is_empty() || prompt.len() > 65_536 {
        return Err("Prompt must contain text and be at most 65536 bytes");
    }
    Ok(Some(prompt.to_owned()))
}

fn selected_observation(
    args: &[OsString],
    task_selected: bool,
) -> Result<Option<String>, &'static str> {
    if args.first().is_none_or(|flag| flag != "--observe-task") {
        return Ok(None);
    }
    let [_, task] = args else {
        return Err("Expected exactly --observe-task TASK_ID");
    };
    if task_selected {
        return Err("--observe-task cannot be combined with AGENT_TASK_ID");
    }
    let task = task.to_str().ok_or("Task ID must be valid Unicode")?;
    selected_task(Ok(task.to_owned()))
}

fn observation_continues(snapshot: &TaskSnapshot, binding: Option<&TaskCorrelation>) -> bool {
    matches!(snapshot.state, TaskState::Submitted | TaskState::Working)
        && binding.is_none_or(|initial| {
            initial.validate_binding(&snapshot.correlation).is_ok()
                && snapshot.terminal_event.validate_binding(initial).is_ok()
        })
}

fn snapshot_status(snapshot: &TaskSnapshot) -> String {
    let state = match snapshot.state {
        TaskState::Submitted => "submitted",
        TaskState::Working => "working",
        TaskState::InputRequired => "input-required",
        TaskState::AuthRequired => "auth-required",
        TaskState::Completed => "completed",
        TaskState::Canceled => "canceled",
        TaskState::Failed => "failed",
        TaskState::Rejected => "rejected",
    };
    format!(
        "Task ID: {}\nContext ID: {}\nRun ID: {}\nState: {state}\n{}",
        snapshot.correlation.task_id(),
        snapshot.correlation.context_id(),
        snapshot.correlation.run_id().unwrap_or("unavailable"),
        snapshot.terminal_event.text(),
    )
}

enum ReadStatus {
    Discovery(String),
    Task(TaskSnapshot),
}

async fn read_status(
    client: &ArboraClient,
    task_id: Option<&str>,
    binding: Option<&TaskCorrelation>,
) -> Result<ReadStatus, &'static str> {
    if let Some(binding) = binding {
        return client.refresh_task(binding).await.map(ReadStatus::Task);
    }
    match task_id {
        Some(task_id) => client.get_task(task_id).await.map(ReadStatus::Task),
        None => client.discover().await.map(ReadStatus::Discovery),
    }
}

fn completed_status(
    result: Result<Result<ReadStatus, &'static str>, tokio::task::JoinError>,
    binding: &mut Option<TaskCorrelation>,
) -> String {
    match result {
        Ok(Ok(ReadStatus::Discovery(name))) => format!("Agent Card received: {name}"),
        Ok(Ok(ReadStatus::Task(mut snapshot))) => {
            if let Some(initial) = binding {
                if let Err(error) = initial.validate_binding(&snapshot.correlation) {
                    return error.to_owned();
                }
                if let Err(error) = snapshot.terminal_event.validate_binding(initial) {
                    return error.to_owned();
                }
                snapshot.correlation = initial.clone();
            } else {
                *binding = Some(snapshot.correlation.clone());
            }
            snapshot_status(&snapshot)
        }
        Ok(Err(error)) => error.to_owned(),
        Err(error) if error.is_cancelled() => {
            "Local read canceled. No remote task was canceled.".to_owned()
        }
        Err(_) => "Read request interrupted".to_owned(),
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
enum Cancellation {
    #[default]
    Unavailable,
    Ready,
    Confirming,
    Pending,
    Unknown,
}

impl Cancellation {
    fn arm(&mut self) {
        if *self == Self::Ready {
            *self = Self::Confirming;
        }
    }

    fn confirm(&mut self) -> bool {
        if *self != Self::Confirming {
            return false;
        }
        *self = Self::Pending;
        true
    }

    fn dismiss(&mut self) {
        if *self == Self::Confirming {
            *self = Self::Ready;
        }
    }

    fn read_started(&mut self) {
        if *self != Self::Unknown {
            *self = Self::Unavailable;
        }
    }
}

const CANCELLATION_UNKNOWN: &str =
    "Cancellation outcome unknown. Press r to read task state before trying again.";

fn request_completed(
    result: Result<Result<ReadStatus, &'static str>, tokio::task::JoinError>,
    binding: &mut Option<TaskCorrelation>,
    cancellation: &mut Cancellation,
    remote_cancel: bool,
) -> String {
    let accepted_state = match &result {
        Ok(Ok(ReadStatus::Task(snapshot)))
            if binding
                .as_ref()
                .is_none_or(|initial| initial.validate_binding(&snapshot.correlation).is_ok()) =>
        {
            Some(snapshot.state)
        }
        _ => None,
    };
    if remote_cancel {
        if binding.is_none() || accepted_state != Some(TaskState::Canceled) {
            *cancellation = Cancellation::Unknown;
            return CANCELLATION_UNKNOWN.to_owned();
        }
    } else if *cancellation == Cancellation::Unknown && accepted_state.is_none() {
        return CANCELLATION_UNKNOWN.to_owned();
    }
    *cancellation = match accepted_state {
        Some(
            TaskState::Submitted
            | TaskState::Working
            | TaskState::InputRequired
            | TaskState::AuthRequired,
        ) => Cancellation::Ready,
        _ => Cancellation::Unavailable,
    };
    completed_status(result, binding)
}

fn submission_completed(
    result: Result<Result<ReadStatus, &'static str>, tokio::task::JoinError>,
    binding: &mut Option<TaskCorrelation>,
    cancellation: &mut Cancellation,
) -> String {
    match result {
        Ok(Ok(ReadStatus::Task(snapshot))) => request_completed(
            Ok(Ok(ReadStatus::Task(snapshot))),
            binding,
            cancellation,
            false,
        ),
        _ => {
            *cancellation = Cancellation::Unavailable;
            SUBMISSION_UNKNOWN.to_owned()
        }
    }
}

async fn run(
    client: Arc<ArboraClient>,
    mut task_id: Option<String>,
    submission: Option<TaskSubmission>,
    observe: bool,
) -> Result<(), &'static str> {
    let theme = env::var("AGENT_THEME").unwrap_or_else(|_| "tokyo-night".to_owned());
    let no_color = env::var("NO_COLOR").unwrap_or_default();
    let style = presentation_style(&theme, &no_color);
    let mut submitting = submission.is_some();
    let loading = if submitting {
        "Submitting Arbora task..."
    } else if task_id.is_some() {
        "Reading Arbora task..."
    } else {
        "Discovering Arbora..."
    };
    let mut terminal = ratatui::init();
    let mut events = EventStream::new();
    let mut request = tokio::spawn({
        let client = client.clone();
        let task_id = task_id.clone();
        async move {
            match submission {
                Some(submission) => client.submit_task(&submission).await.map(ReadStatus::Task),
                None => read_status(&client, task_id.as_deref(), None).await,
            }
        }
    });
    let mut pending = true;
    let mut observation_active = observe;
    let mut observation_tick = tokio::time::interval(std::time::Duration::from_millis(500));
    observation_tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut status = loading.to_owned();
    let mut binding = None;
    let mut cancellation = Cancellation::default();
    let mut remote_cancel = false;
    let mut submission_unknown = false;
    let mut viewport = Viewport::default();
    let mut inspector = InspectorView::default();
    let mut logs = HostLogView::default();
    let mut redraw = tokio::time::interval(std::time::Duration::from_millis(250));
    redraw.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let result = async {
        loop {
            let mut confirmation_visible = false;
            terminal.draw(|frame| {
                if cancellation == Cancellation::Confirming {
                    confirmation_visible = draw_confirmation(frame, &status, style);
                } else if logs.is_open() {
                    logs.draw(frame, style);
                } else if inspector.is_open() {
                    inspector.draw(frame, style, std::time::Instant::now());
                } else {
                    draw_viewport(frame, &status, style, &mut viewport, observe);
                }
            }).map_err(|_| "Cannot draw terminal")?;
            tokio::select! {
                result = &mut request, if pending => {
                    pending = false;
                    observation_active = observe && matches!(&result,
                        Ok(Ok(ReadStatus::Task(snapshot))) if observation_continues(snapshot, binding.as_ref()));
                    let accepted = matches!(&result, Ok(Ok(ReadStatus::Task(snapshot)))
                        if binding.as_ref().is_none_or(|bound: &TaskCorrelation| bound.validate_binding(&snapshot.correlation).is_ok()));
                    if submitting {
                        status = submission_completed(result, &mut binding, &mut cancellation);
                        task_id = binding.as_ref().map(|bound| bound.task_id().to_owned());
                        submission_unknown = binding.is_none();
                        submitting = false;
                    } else {
                        status = request_completed(result, &mut binding, &mut cancellation, remote_cancel);
                    }
                    inspector.task_updated(if accepted { binding.as_ref() } else { None });
                }
                _ = observation_tick.tick(), if observation_active && !pending => {
                    status = "Reading Arbora task...".to_owned();
                    let client = client.clone();
                    let task_id = task_id.clone();
                    let read_binding = binding.clone();
                    request = tokio::spawn(async move {
                        read_status(&client, task_id.as_deref(), read_binding.as_ref()).await
                    });
                    pending = true;
                    remote_cancel = false;
                    cancellation.read_started();
                }
                _ = inspector.complete(), if inspector.pending() => {}
                _ = logs.complete(), if logs.pending() => {}
                _ = redraw.tick(), if inspector.is_open() || logs.is_open() => { logs.tick(); }
                event = events.next() => {
                    let Some(Ok(event)) = event else { return Err("Terminal input unavailable"); };
                    if let Event::Key(key) = event {
                        if key.kind != KeyEventKind::Press { continue; }
                        if key.code == KeyCode::Char('q') || (key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL)) {
                            return Ok(());
                        }
                        if cancellation != Cancellation::Confirming {
                            if logs.key(key.code) { continue; }
                            if (key.code == KeyCode::Char('l') || (key.code == KeyCode::Char('v') && key.modifiers.contains(KeyModifiers::CONTROL))) && !inspector.is_open() {
                                logs.open(client.clone());
                                continue;
                            }
                            if inspector.key(key.code, client.clone()) { continue; }
                            if key.code == KeyCode::Char('i') && !pending {
                                inspector.open(client.clone());
                                continue;
                            }
                            if viewport.handle(key.code) { continue; }
                        }
                        match key.code {
                            KeyCode::Char('c') if pending => {
                                observation_active = false;
                                request.abort();
                                inspector.task_updated(None);
                                pending = false;
                                let result = (&mut request).await;
                                if submitting {
                                    status = submission_completed(result, &mut binding, &mut cancellation);
                                    task_id = binding.as_ref().map(|bound| bound.task_id().to_owned());
                                    submission_unknown = binding.is_none();
                                    submitting = false;
                                } else if remote_cancel {
                                    cancellation = Cancellation::Unknown;
                                    status = CANCELLATION_UNKNOWN.to_owned();
                                } else {
                                    status = request_completed(result, &mut binding, &mut cancellation, false);
                                }
                            }
                            KeyCode::Char('r') if !pending && !submission_unknown => {
                                status = if task_id.is_some() { "Reading Arbora task..." } else { "Discovering Arbora..." }.to_owned();
                                let client = client.clone();
                                let task_id = task_id.clone();
                                let read_binding = binding.clone();
                                request = tokio::spawn(async move { read_status(&client, task_id.as_deref(), read_binding.as_ref()).await });
                                pending = true;
                                remote_cancel = false;
                                cancellation.read_started();
                            }
                            KeyCode::Char('x') if !pending && !observe => cancellation.arm(),
                            KeyCode::Char('n') | KeyCode::Esc => cancellation.dismiss(),
                            KeyCode::Char('y') if !observe && !pending && confirm_visible(&mut cancellation, confirmation_visible, crossterm::terminal::size()) => {
                                if let Some(binding) = binding.clone() {
                                    let client = client.clone();
                                    request = tokio::spawn(async move {
                                        client.cancel_task(&binding).await.map(ReadStatus::Task)
                                    });
                                    pending = true;
                                    remote_cancel = true;
                                    status = "Canceling remote task...".to_owned();
                                }
                            }
                            _ => {}
                        }
                    }
                }
            }
        }
    }.await;
    request.abort();
    inspector.close();
    logs.close();
    ratatui::restore();
    if submitting {
        status = submission_completed((&mut request).await, &mut binding, &mut cancellation);
        eprintln!("{status}");
    } else if submission_unknown {
        eprintln!("{SUBMISSION_UNKNOWN}");
    }
    result
}

#[tokio::main]
async fn main() -> ExitCode {
    let endpoint = env::var("AGENT_URL").unwrap_or_else(|_| "http://localhost:8000".to_owned());
    let token = env::var("AGENT_BEARER_TOKEN").ok();
    let result = async {
        let task_id = selected_task(env::var("AGENT_TASK_ID"))?;
        let args: Vec<_> = env::args_os().skip(1).collect();
        let observation = selected_observation(&args, task_id.is_some())?;
        let observe = observation.is_some();
        if observe && token.is_none() {
            return Err("Observation requires a caller credential");
        }
        let prompt = if observe {
            None
        } else {
            selected_prompt(&args, task_id.is_some())?
        };
        let task_id = observation.or(task_id);
        if prompt.is_some() && token.is_none() {
            return Err("Submission requires a caller credential");
        }
        let submission = prompt.as_deref().map(TaskSubmission::new).transpose()?;
        let client = ArboraClient::new(&endpoint, token.as_deref())?;
        run(Arc::new(client), task_id, submission, observe).await
    }
    .await;
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{
        CANCELLATION_UNKNOWN, Cancellation, ReadStatus, SUBMISSION_UNKNOWN, completed_status, draw,
        presentation_style, request_completed, selected_prompt, selected_task, snapshot_status,
        submission_completed,
    };
    use agent_terminal_ui_native::{
        TaskSnapshot,
        correlation::{TaskCorrelation, TaskState},
    };
    use ratatui::style::{Color, Style};
    use ratatui::{Terminal, backend::TestBackend};
    use std::env::VarError;
    use std::ffi::OsString;

    // spec: TUI-RUNTIME-R002.1.3.1
    #[test]
    fn prompt_arguments_allow_only_one_text_submission() {
        let arguments = |values: &[&str]| values.iter().map(OsString::from).collect::<Vec<_>>();
        assert_eq!(selected_prompt(&[], false), Ok(None));
        assert_eq!(selected_prompt(&[], true), Ok(None));
        assert_eq!(
            selected_prompt(&arguments(&["--prompt", "ordinary text"]), false),
            Ok(Some("ordinary text".to_owned()))
        );
        for invalid in [
            vec!["--prompt"],
            vec!["ordinary text"],
            vec!["--override", "text"],
            vec!["--prompt", "text", "--prompt", "again"],
            vec!["--prompt", "text", "extra"],
            vec!["--prompt", "  "],
            vec!["--prompt=other"],
        ] {
            assert!(selected_prompt(&arguments(&invalid), false).is_err());
        }
        assert!(selected_prompt(&arguments(&["--prompt", "text"]), true).is_err());
        assert!(selected_prompt(&arguments(&["--prompt", &"x".repeat(65_537)]), false).is_err());
    }

    // spec: TUI-RUNTIME-R002.1.3.1
    #[test]
    fn accepted_submission_binds_returned_task_and_enables_cancellation() {
        let mut binding = None;
        let mut cancellation = Cancellation::Unavailable;
        let status = submission_completed(
            Ok(Ok(task_read(
                "returned-task",
                "returned-context",
                Some("returned-run"),
            ))),
            &mut binding,
            &mut cancellation,
        );
        assert!(status.contains("Task ID: returned-task"));
        assert_eq!(binding.unwrap().context_id(), "returned-context");
        assert_eq!(cancellation, Cancellation::Ready);
    }

    // spec: TUI-RUNTIME-R002.1.3.1
    #[tokio::test]
    async fn uncertain_submission_never_supplies_task_authority() {
        let mut binding = None;
        let mut cancellation = Cancellation::Unavailable;
        for result in [
            Ok(Err("protected response detail")),
            Ok(Ok(ReadStatus::Discovery("unexpected".to_owned()))),
        ] {
            assert_eq!(
                submission_completed(result, &mut binding, &mut cancellation),
                SUBMISSION_UNKNOWN
            );
            assert!(binding.is_none());
            assert_eq!(cancellation, Cancellation::Unavailable);
        }
        let request = tokio::spawn(async {
            std::future::pending::<Result<ReadStatus, &'static str>>().await
        });
        request.abort();
        assert_eq!(
            submission_completed(request.await, &mut binding, &mut cancellation),
            SUBMISSION_UNKNOWN
        );
        assert!(binding.is_none());
    }

    // spec: TUI-RUNTIME-R002.1.3.1
    #[tokio::test]
    async fn abort_after_submission_completes_retains_known_binding() {
        let request = tokio::spawn(async {
            Ok(task_read(
                "accepted-task",
                "accepted-context",
                Some("accepted-run"),
            ))
        });
        while !request.is_finished() {
            tokio::task::yield_now().await;
        }
        request.abort();
        let mut binding = None;
        let mut cancellation = Cancellation::Unavailable;
        let status = submission_completed(request.await, &mut binding, &mut cancellation);
        let binding = binding.unwrap();
        assert_eq!(binding.task_id(), "accepted-task");
        assert_eq!(binding.context_id(), "accepted-context");
        assert_eq!(binding.run_id(), Some("accepted-run"));
        assert!(status.contains("Task ID: accepted-task"));
        assert!(!status.contains("outcome unknown"));
        assert_eq!(cancellation, Cancellation::Ready);
    }

    fn task_read(task_id: &str, context_id: &str, run_id: Option<&str>) -> ReadStatus {
        let mut task = serde_json::json!({
            "kind": "task", "id": task_id, "contextId": context_id,
            "status": {"state": "working"}
        });
        if let Some(run_id) = run_id {
            task["metadata"] = serde_json::json!({"arbora": {"runId": run_id}});
        }
        ReadStatus::Task(TaskSnapshot {
            terminal_event: Default::default(),
            correlation: TaskCorrelation::from_task(&task).unwrap(),
            state: TaskState::Working,
        })
    }

    // spec: TUI-RUNTIME-R002.1.4
    #[test]
    fn refresh_rejects_changed_binding_and_retains_omitted_run() {
        let mut binding = None;
        completed_status(
            Ok(Ok(task_read("task-one", "context-two", Some("run-three")))),
            &mut binding,
        );
        let initial = binding.clone();
        for changed in [
            task_read("other-task", "context-two", Some("run-three")),
            task_read("task-one", "other-context", Some("run-three")),
            task_read("task-one", "context-two", Some("other-run")),
        ] {
            let status = completed_status(Ok(Ok(changed)), &mut binding);
            assert_eq!(status, "Task correlation mismatch");
            assert_eq!(binding, initial);
        }
        let status = completed_status(
            Ok(Ok(task_read("task-one", "context-two", None))),
            &mut binding,
        );
        assert!(status.contains("Run ID: run-three"));
        assert_eq!(binding, initial);
    }

    // spec: TUI-RUNTIME-R002.1.4
    #[test]
    fn refresh_does_not_acquire_a_later_run_binding() {
        let mut binding = None;
        completed_status(
            Ok(Ok(task_read("task-one", "context-two", None))),
            &mut binding,
        );
        let status = completed_status(
            Ok(Ok(task_read("task-one", "context-two", Some("later-run")))),
            &mut binding,
        );
        assert_eq!(status, "Task correlation mismatch");
        assert_eq!(binding.as_ref().unwrap().run_id(), None);
    }

    // spec: TUI-RUNTIME-R002.1.4
    #[tokio::test]
    async fn denial_and_local_cancellation_preserve_initial_binding() {
        let mut binding = None;
        completed_status(
            Ok(Ok(task_read("task-one", "context-two", Some("run-three")))),
            &mut binding,
        );
        let initial = binding.clone();
        assert_eq!(
            completed_status(
                Ok(Err("Arbora task read refused or unavailable")),
                &mut binding
            ),
            "Arbora task read refused or unavailable"
        );
        assert_eq!(binding, initial);
        let request = tokio::spawn(std::future::pending::<Result<ReadStatus, &'static str>>());
        request.abort();
        assert_eq!(
            completed_status(request.await, &mut binding),
            "Local read canceled. No remote task was canceled."
        );
        assert_eq!(binding, initial);
        assert_eq!(
            completed_status(
                Ok(Ok(task_read(
                    "task-one",
                    "other-context",
                    Some("run-three")
                ))),
                &mut binding,
            ),
            "Task correlation mismatch"
        );
    }

    // spec: TUI-RUNTIME-R002.7
    #[test]
    fn renders_refusal_without_enabling_task_actions() {
        let mut terminal = Terminal::new(TestBackend::new(100, 10)).unwrap();
        terminal
            .draw(|frame| {
                draw(
                    frame,
                    "Arbora discovery refused or unavailable",
                    Style::default(),
                )
            })
            .unwrap();
        let text: String = terminal
            .backend()
            .buffer()
            .content()
            .iter()
            .map(|cell| cell.symbol())
            .collect();
        assert!(text.contains("Arbora discovery refused"));
        assert!(text.contains("Task streaming and approvals remain unavailable"));
    }

    // spec: TUI-RUNTIME-R008.1
    #[test]
    fn resize_preserves_wrapped_status_and_keyboard_help() {
        let mut terminal = Terminal::new(TestBackend::new(100, 16)).unwrap();
        let status = "Local discovery canceled. No remote task was canceled.";
        for width in [100, 40, 100] {
            terminal.backend_mut().resize(width, 16);
            terminal.autoresize().unwrap();
            terminal
                .draw(|frame| draw(frame, status, Style::default()))
                .unwrap();
            let buffer = terminal.backend().buffer();
            let lines: Vec<String> = (1..15)
                .map(|y| (1..width - 1).map(|x| buffer[(x, y)].symbol()).collect())
                .collect();
            let text = lines
                .iter()
                .map(|line| line.trim())
                .collect::<Vec<_>>()
                .join(" ");
            assert!(
                text.contains(status),
                "status clipped at {width} columns: {text}"
            );
            for help in [
                "r: refresh read",
                "c: cancel local request",
                "q / Ctrl+C: quit",
            ] {
                assert!(
                    text.contains(help),
                    "help clipped at {width} columns: {text}"
                );
            }
        }
    }

    // spec: TUI-RUNTIME-R008.1
    #[test]
    fn renderer_honors_no_color_and_unknown_theme_fallback() {
        let default_style = presentation_style("tokyo-night", "");
        assert_eq!(presentation_style("unknown-theme", ""), default_style);
        let mut terminal = Terminal::new(TestBackend::new(40, 16)).unwrap();
        for (theme, no_color) in [
            ("tokyo-night", ""),
            ("unknown-theme", ""),
            ("tokyo-night", "1"),
            ("unknown-theme", "0"),
        ] {
            terminal
                .draw(|frame| {
                    draw(
                        frame,
                        "Discovering Arbora...",
                        presentation_style(theme, no_color),
                    )
                })
                .unwrap();
            let cell = &terminal.backend().buffer()[(1, 1)];
            if no_color.is_empty() {
                assert_eq!(cell.fg, Color::Rgb(169, 177, 214));
                assert_eq!(cell.bg, Color::Rgb(26, 27, 38));
            } else {
                assert!(
                    terminal
                        .backend()
                        .buffer()
                        .content()
                        .iter()
                        .all(|cell| cell.fg == Color::Reset && cell.bg == Color::Reset)
                );
            }
        }
    }

    // spec: TUI-RUNTIME-R002.1.4
    #[test]
    fn task_view_renders_distinct_identifiers_and_missing_run() {
        let mut terminal = Terminal::new(TestBackend::new(100, 16)).unwrap();
        for run_id in [None, Some("run-three")] {
            let mut task = serde_json::json!({
                "kind": "task", "id": "task-one", "contextId": "context-two",
                "status": {"state": "working"}
            });
            if let Some(run_id) = run_id {
                task["metadata"] = serde_json::json!({"arbora": {"runId": run_id}});
            }
            let snapshot = TaskSnapshot {
                terminal_event: Default::default(),
                correlation: TaskCorrelation::from_task(&task).unwrap(),
                state: TaskState::Working,
            };
            terminal
                .draw(|frame| draw(frame, &snapshot_status(&snapshot), Style::default()))
                .unwrap();
            let text: String = terminal
                .backend()
                .buffer()
                .content()
                .iter()
                .map(|cell| cell.symbol())
                .collect();
            assert!(text.contains("Task ID: task-one"));
            assert!(text.contains("Context ID: context-two"));
            assert!(text.contains(&format!("Run ID: {}", run_id.unwrap_or("unavailable"))));
            assert!(text.contains("State: working"));
            let refused = completed_status(
                Ok(Err("Arbora task read refused or unavailable")),
                &mut Some(snapshot.correlation.clone()),
            );
            terminal
                .draw(|frame| draw(frame, &refused, Style::default()))
                .unwrap();
            let text: String = terminal
                .backend()
                .buffer()
                .content()
                .iter()
                .map(|cell| cell.symbol())
                .collect();
            assert!(text.contains("Arbora task read refused or unavailable"));
            for protected in ["task-one", "context-two", "run-three", "State: working"] {
                assert!(!text.contains(protected));
            }
        }
    }

    // spec: TUI-RUNTIME-R002.1.4
    #[test]
    fn task_selection_rejects_empty_and_control_identifiers() {
        assert_eq!(selected_task(Err(VarError::NotPresent)), Ok(None));
        assert_eq!(
            selected_task(Ok("task-one".to_owned())),
            Ok(Some("task-one".to_owned()))
        );
        for invalid in ["", " ", "task\nsecret", "task\u{1b}"] {
            assert!(selected_task(Ok(invalid.to_owned())).is_err());
        }
    }

    // spec: TUI-RUNTIME-R002.1.5
    #[test]
    fn cancellation_requires_confirmation_and_consumes_it_once() {
        let mut cancellation = Cancellation::Unavailable;
        cancellation.arm();
        assert!(!cancellation.confirm());
        cancellation = Cancellation::Ready;
        cancellation.arm();
        cancellation.dismiss();
        assert!(!cancellation.confirm());
        cancellation.arm();
        assert!(cancellation.confirm());
        cancellation.arm();
        assert!(!cancellation.confirm());
        assert_eq!(cancellation, Cancellation::Pending);
    }

    // spec: TUI-RUNTIME-R002.1.5
    #[tokio::test]
    async fn uncertain_cancellation_requires_successful_read_and_hides_snapshot() {
        let mut binding = None;
        let mut cancellation = Cancellation::Unavailable;
        request_completed(
            Ok(Ok(task_read("task-one", "context-two", Some("run-three")))),
            &mut binding,
            &mut cancellation,
            false,
        );
        let initial = binding.clone();
        let request = tokio::spawn(std::future::pending::<Result<ReadStatus, &'static str>>());
        request.abort();
        let status = request_completed(request.await, &mut binding, &mut cancellation, true);
        assert_eq!(status, CANCELLATION_UNKNOWN);
        assert!(!status.contains("No remote task was canceled"));
        for protected in ["task-one", "context-two", "run-three"] {
            assert!(!status.contains(protected));
        }
        cancellation.arm();
        assert!(!cancellation.confirm());
        cancellation.read_started();
        assert_eq!(
            request_completed(Ok(Err("refused")), &mut binding, &mut cancellation, false),
            CANCELLATION_UNKNOWN
        );
        assert_eq!(binding, initial);
        assert_eq!(cancellation, Cancellation::Unknown);
        request_completed(
            Ok(Ok(task_read("task-one", "context-two", None))),
            &mut binding,
            &mut cancellation,
            false,
        );
        assert_eq!(cancellation, Cancellation::Ready);
        assert_eq!(binding, initial);
    }

    // spec: TUI-RUNTIME-R002.1.5
    #[test]
    fn only_bound_canceled_response_confirms_remote_cancellation() {
        let mut binding = None;
        let mut cancellation = Cancellation::Unavailable;
        request_completed(
            Ok(Ok(task_read("task-one", "context-two", None))),
            &mut binding,
            &mut cancellation,
            false,
        );
        assert_eq!(
            request_completed(
                Ok(Ok(task_read("task-one", "context-two", None))),
                &mut binding,
                &mut cancellation,
                true
            ),
            CANCELLATION_UNKNOWN
        );
        let ReadStatus::Task(mut canceled) = task_read("task-one", "context-two", None) else {
            panic!("expected task")
        };
        canceled.state = TaskState::Canceled;
        let mut unbound = None;
        assert_eq!(
            request_completed(
                Ok(Ok(ReadStatus::Task(canceled.clone()))),
                &mut unbound,
                &mut cancellation,
                true
            ),
            CANCELLATION_UNKNOWN
        );
        assert!(unbound.is_none());
        let ReadStatus::Task(mut mismatch) = task_read("other-task", "context-two", None) else {
            panic!("expected task")
        };
        mismatch.state = TaskState::Canceled;
        assert_eq!(
            request_completed(
                Ok(Ok(ReadStatus::Task(mismatch))),
                &mut binding,
                &mut cancellation,
                true
            ),
            CANCELLATION_UNKNOWN
        );
        let status = request_completed(
            Ok(Ok(ReadStatus::Task(canceled))),
            &mut binding,
            &mut cancellation,
            true,
        );
        assert!(status.contains("State: canceled"));
        assert_eq!(cancellation, Cancellation::Unavailable);
        cancellation.arm();
        assert!(!cancellation.confirm());
    }

    // spec: TUI-RUNTIME-R002.1.5
    #[test]
    fn discovery_failed_reads_and_terminal_tasks_do_not_arm_cancellation() {
        let mut binding = None;
        let mut cancellation = Cancellation::Unavailable;
        request_completed(
            Ok(Ok(ReadStatus::Discovery("Agent".to_owned()))),
            &mut binding,
            &mut cancellation,
            false,
        );
        cancellation.arm();
        assert!(!cancellation.confirm());
        request_completed(
            Ok(Ok(task_read("task-one", "context-two", None))),
            &mut binding,
            &mut cancellation,
            false,
        );
        request_completed(Ok(Err("refused")), &mut binding, &mut cancellation, false);
        cancellation.arm();
        assert!(!cancellation.confirm());
        for state in [
            TaskState::Completed,
            TaskState::Canceled,
            TaskState::Failed,
            TaskState::Rejected,
        ] {
            let ReadStatus::Task(mut snapshot) = task_read("task-one", "context-two", None) else {
                panic!("expected task")
            };
            snapshot.state = state;
            request_completed(
                Ok(Ok(ReadStatus::Task(snapshot))),
                &mut binding,
                &mut cancellation,
                false,
            );
            cancellation.arm();
            assert!(!cancellation.confirm());
        }
    }
}

#[cfg(test)]
mod confirmation_view_tests {
    use super::*;
    use ratatui::{Terminal, backend::TestBackend};

    // spec: TUI-RUNTIME-R008.2.2
    #[test]
    fn confirmation_is_pinned_and_small_terminals_cannot_confirm() {
        let status =
            "Task ID: task-one\nContext ID: context-two\nRun ID: run-three\nState: working";
        let mut terminal = Terminal::new(TestBackend::new(40, 10)).unwrap();
        let mut viewport = Viewport::default();
        terminal
            .draw(|frame| draw_viewport(frame, status, Style::default(), &mut viewport, false))
            .unwrap();
        viewport.handle(KeyCode::End);
        for (width, height, allowed) in [
            (40, 10, true),
            (34, 5, true),
            (33, 5, false),
            (34, 4, false),
        ] {
            terminal.backend_mut().resize(width, height);
            terminal.autoresize().unwrap();
            let mut visible = false;
            terminal
                .draw(|frame| visible = draw_confirmation(frame, status, Style::default()))
                .unwrap();
            assert_eq!(visible, allowed);
            if allowed {
                let buffer = terminal.backend().buffer();
                let first: String = (1..width - 1).map(|x| buffer[(x, 1)].symbol()).collect();
                let second: String = (1..width - 1).map(|x| buffer[(x, 2)].symbol()).collect();
                assert!(first.contains("Cancel selected remote task?"));
                assert!(second.contains("y: confirm | n / Escape: dismiss"));
            }
            let mut cancellation = Cancellation::Confirming;
            assert!(!confirm_visible(&mut cancellation, true, Ok((10, 2))));
            assert!(!confirm_visible(
                &mut cancellation,
                true,
                Err(std::io::Error::other("size unavailable"))
            ));
            assert_eq!(
                confirm_visible(&mut cancellation, visible, Ok((width, height))),
                allowed
            );
            assert_eq!(
                cancellation,
                if allowed {
                    Cancellation::Pending
                } else {
                    Cancellation::Confirming
                }
            );
        }
    }
}
#[cfg(test)]
mod recovery_view_tests;

#[cfg(test)]
mod terminal_point_view_tests {
    use super::*;
    use agent_terminal_ui_native::terminal_event::TerminalEvent;
    use ratatui::{Terminal, backend::TestBackend};
    use serde_json::json;

    // spec: TUI-RUNTIME-R002.1.3.2.2.3
    #[test]
    fn committed_identity_renders_literally_and_failed_read_clears_it() {
        let task = json!({"kind":"task","id":"task","contextId":"ctx","status":{"state":"completed"},
        "metadata":{"arbora":{"runId":"run","terminalEvent":{
            "status":"available","tenant":"tenant","scope":{"tenant":"tenant","scope":{"kind":"graph","graph":"graph"},"incarnation_id":"inc","identity_digest":vec![170;32]},
            "batch_id":"[bold]actual-batch","commit_sequence":7,"ordinal":0,"run_id":"run","kind":"outcome","outcome":"succeeded","result_ref":null,"payload_digest":"b".repeat(64)
        }}}});
        let correlation = TaskCorrelation::from_task(&task).unwrap();
        let snapshot = TaskSnapshot {
            terminal_event: TerminalEvent::from_task(&task, &correlation, TaskState::Completed)
                .unwrap(),
            correlation,
            state: TaskState::Completed,
        };
        let mut binding = None;
        let status = completed_status(Ok(Ok(ReadStatus::Task(snapshot))), &mut binding);
        let mut terminal = Terminal::new(TestBackend::new(120, 30)).unwrap();
        terminal
            .draw(|frame| draw(frame, &status, Style::default()))
            .unwrap();
        let text: String = terminal
            .backend()
            .buffer()
            .content()
            .iter()
            .map(|cell| cell.symbol())
            .collect();
        assert!(text.contains("[bold]actual-batch"));
        assert!(text.contains("Commit sequence: 7"));
        let failed = completed_status(Ok(Err("read refused")), &mut binding);
        terminal
            .draw(|frame| draw(frame, &failed, Style::default()))
            .unwrap();
        let text: String = terminal
            .backend()
            .buffer()
            .content()
            .iter()
            .map(|cell| cell.symbol())
            .collect();
        assert!(!text.contains("actual-batch"));
        assert!(!text.contains("Commit sequence: 7"));
    }

    #[test]
    fn observation_arguments_are_explicit_and_exclusive() {
        let arguments = |values: &[&str]| values.iter().map(OsString::from).collect::<Vec<_>>();
        assert_eq!(
            super::selected_observation(&arguments(&["--observe-task", "task-1"]), false),
            Ok(Some("task-1".to_owned()))
        );
        for values in [
            vec!["--observe-task"],
            vec!["--observe-task", ""],
            vec!["--observe-task", "x", "--prompt", "effect"],
            vec!["--observe-task", "x", "--override"],
            vec!["--observe-task", "bad\nidentity"],
        ] {
            assert!(super::selected_observation(&arguments(&values), false).is_err());
        }
        assert!(super::selected_observation(&arguments(&["--observe-task", "x"]), true).is_err());
        assert!(
            super::selected_observation(&arguments(&["--observe-task", &"x".repeat(513)]), false)
                .is_err()
        );
    }

    #[test]
    fn observation_polling_requires_active_matching_task() {
        let ReadStatus::Task(mut snapshot) =
            task_read("task-one", "context-two", Some("run-three"))
        else {
            panic!("task fixture required")
        };
        let initial = snapshot.correlation.clone();
        for state in [TaskState::Submitted, TaskState::Working] {
            snapshot.state = state;
            assert!(super::observation_continues(&snapshot, Some(&initial)));
        }
        for state in [
            TaskState::InputRequired,
            TaskState::AuthRequired,
            TaskState::Completed,
            TaskState::Failed,
            TaskState::Rejected,
            TaskState::Canceled,
        ] {
            snapshot.state = state;
            assert!(!super::observation_continues(&snapshot, Some(&initial)));
        }
        snapshot.state = TaskState::Working;
        let ReadStatus::Task(other) = task_read("task-one", "other-context", Some("run-three"))
        else {
            panic!("task fixture required")
        };
        assert!(!super::observation_continues(
            &snapshot,
            Some(&other.correlation)
        ));
    }

    #[test]
    fn observation_help_does_not_offer_remote_cancellation() {
        let mut terminal = Terminal::new(TestBackend::new(180, 12)).unwrap();
        terminal
            .draw(|frame| {
                super::draw_viewport(
                    frame,
                    "Task ID: task-one",
                    Style::default(),
                    &mut super::Viewport::default(),
                    true,
                )
            })
            .unwrap();
        let text: String = terminal
            .backend()
            .buffer()
            .content()
            .iter()
            .map(|cell| cell.symbol())
            .collect();
        assert!(text.contains("read-only observation"));
        assert!(!text.contains("x: cancel remote task"));
        assert!(text.contains("r: refresh read"));
    }
}
