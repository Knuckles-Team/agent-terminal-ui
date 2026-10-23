use crate::presentation::Viewport;
use agent_terminal_ui_native::{
    ArboraClient,
    correlation::TaskCorrelation,
    run_inspector::{ReadRefusal, RunInspector},
    run_inspector_client::RunRead,
};
use crossterm::event::{KeyCode, MouseEvent};
use ratatui::{
    Frame,
    style::Style,
    widgets::{Block, Paragraph, Wrap},
};
use std::{sync::Arc, time::Instant};
use tokio::task::JoinHandle;

type ReadTask = JoinHandle<Result<RunRead, ReadRefusal>>;

#[derive(Default)]
pub struct InspectorView {
    binding: Option<TaskCorrelation>,
    inspector: Option<RunInspector>,
    request: Option<ReadTask>,
    open: bool,
    viewport: Viewport,
}

impl InspectorView {
    pub fn is_open(&self) -> bool {
        self.open
    }
    pub fn pending(&self) -> bool {
        self.request.is_some()
    }

    /// Only a successful, correlated task read may select a run.
    pub fn task_updated(&mut self, binding: Option<&TaskCorrelation>) {
        let run = binding.and_then(TaskCorrelation::run_id);
        if binding != self.binding.as_ref() || binding.is_none() {
            self.abort();
            self.binding = binding.cloned();
            self.inspector = run.map(|run| RunInspector::new(run.to_owned()));
            self.viewport = Viewport::default();
        }
    }

    pub fn open(&mut self, client: Arc<ArboraClient>) {
        self.open = true;
        self.refresh(client);
    }

    fn refresh(&mut self, client: Arc<ArboraClient>) {
        if self.pending() {
            return;
        }
        let Some(binding) = self.binding.as_ref() else {
            return;
        };
        let Some(run) = binding.run_id().map(str::to_owned) else {
            return;
        };
        let task = binding.task_id().to_owned();
        self.clear_read();
        self.request = Some(tokio::spawn(
            async move { client.get_run(&run, &task).await },
        ));
    }

    fn clear_read(&mut self) {
        if let Some(inspector) = &mut self.inspector {
            let _ = inspector.accept_read(Err(ReadRefusal::Unavailable), Instant::now());
        }
    }

    fn abort(&mut self) {
        if let Some(request) = self.request.take() {
            request.abort();
        }
        self.clear_read();
    }

    pub fn close(&mut self) {
        self.abort();
        self.open = false;
    }

    pub async fn complete(&mut self) {
        let result = match self.request.as_mut() {
            Some(request) => request.await.unwrap_or(Err(ReadRefusal::Unavailable)),
            None => return,
        };
        self.request = None;
        if let Some(inspector) = &mut self.inspector {
            let _ = inspector.accept_read(result, Instant::now());
        }
    }

    /// An open read-only inspector consumes keys, including effect shortcuts.
    pub fn key(&mut self, key: KeyCode, client: Arc<ArboraClient>) -> bool {
        if !self.open {
            return false;
        }
        match key {
            KeyCode::Esc => self.close(),
            KeyCode::Char('c') => self.abort(),
            KeyCode::Char('r') | KeyCode::Char('i') => self.refresh(client),
            _ => {
                self.viewport.handle(key);
            }
        }
        true
    }

    fn text(&mut self, now: Instant) -> String {
        let body = match &mut self.inspector {
            Some(inspector) => inspector.text(now),
            None => "Run inspector unavailable: no validated run binding".to_owned(),
        };
        let state = if self.pending() {
            "Reading run...\n"
        } else {
            ""
        };
        format!("{state}{body}\n\nr / i: refresh | c: cancel local read | Escape: close | q: quit")
    }

    pub fn mouse(&mut self, event: MouseEvent) -> bool {
        self.open && self.viewport.mouse(event)
    }

    pub fn draw(&mut self, frame: &mut Frame, style: Style, now: Instant) {
        let paragraph = Paragraph::new(self.text(now))
            .style(style)
            .wrap(Wrap { trim: false });
        let block = Block::bordered()
            .title("Run inspector (read-only)")
            .title_bottom("PgUp/PgDn Home/End");
        let inner = block.inner(frame.area());
        self.viewport
            .measure(paragraph.line_count(inner.width), inner.height);
        frame.render_widget(
            paragraph.scroll((self.viewport.offset(), 0)).block(block),
            frame.area(),
        );
    }
}

impl Drop for InspectorView {
    fn drop(&mut self) {
        self.abort();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use agent_terminal_ui_native::run_inspector::{
        AppliedConfig, PlanItem, PlanRefusal, PlanSnapshot, PlanStatus, PlanValidator,
        RunProjection,
    };
    use ratatui::{Terminal, backend::TestBackend};
    use serde_json::json;
    use std::time::Duration;

    fn binding(run: Option<&str>) -> TaskCorrelation {
        let mut task =
            json!({"kind":"task","id":"task","contextId":"ctx","status":{"state":"working"}});
        if let Some(run) = run {
            task["metadata"] = json!({"arbora":{"runId":run}});
        }
        TaskCorrelation::from_task(&task).unwrap()
    }
    fn client() -> Arc<ArboraClient> {
        Arc::new(ArboraClient::new("http://127.0.0.1:1", None).unwrap())
    }
    struct ValidUntil(Instant);
    impl PlanValidator for ValidUntil {
        fn validate(
            &self,
            _: &PlanSnapshot,
            _: Option<&str>,
            _: Instant,
        ) -> Result<Instant, PlanRefusal> {
            Ok(self.0)
        }
    }
    fn populated(now: Instant) -> InspectorView {
        let mut view = InspectorView::default();
        view.task_updated(Some(&binding(Some("run-one"))));
        view.open = true;
        view.inspector
            .as_mut()
            .unwrap()
            .accept(
                Ok(RunProjection {
                    run_id: "run-one".into(),
                    peak_context_tokens: Some(42),
                    context_budget_tokens: None,
                    cost_usd: Some(0.0),
                    termination_reason: None,
                    config: AppliedConfig::default(),
                    current_plan: Some(PlanSnapshot {
                        run_id: "run-one".into(),
                        revision: "1".into(),
                        observed_at: "fixture".into(),
                        items: vec![PlanItem {
                            text: "private-plan".into(),
                            status: PlanStatus::Pending,
                        }],
                    }),
                }),
                Some(&ValidUntil(now + Duration::from_secs(1))),
                now,
            )
            .unwrap();
        view
    }

    // spec: TUI-RUNTIME-R010.9
    #[test]
    fn selection_uses_only_task_run_and_clears_on_failure_or_change() {
        let now = Instant::now();
        for selection in [None, Some(binding(None)), Some(binding(Some("other-run")))] {
            let mut view = populated(now);
            assert!(view.text(now).contains("private-plan"));
            view.task_updated(selection.as_ref());
            let text = view.text(now);
            assert!(!text.contains("private-plan"));
            assert!(!text.contains("Peak context tokens: 42"));
            assert!(!text.contains("run-one"));
        }
        let mut view = populated(now);
        view.task_updated(Some(&binding(Some("run-one"))));
        assert!(view.text(now).contains("private-plan"));
    }

    // spec: TUI-RUNTIME-R008.2.3.2.2.1
    #[test]
    fn same_run_with_a_different_owner_or_context_clears_inspector_values() {
        let now = Instant::now();
        for (task, context) in [("work-item:owner", "ctx"), ("task", "other-context")] {
            let mut view = populated(now);
            let binding = TaskCorrelation::from_task(&json!({
                "kind":"task", "id":task, "contextId":context,
                "status":{"state":"working"},
                "metadata":{"arbora":{"runId":"run-one"}}
            }))
            .unwrap();
            view.task_updated(Some(&binding));
            assert!(!view.text(now).contains("private-plan"));
            assert!(!view.text(now).contains("Peak context tokens: 42"));
            assert_eq!(view.binding.as_ref().unwrap().task_id(), task);
        }
    }

    // spec: TUI-RUNTIME-R010.9
    #[tokio::test]
    async fn denied_or_panicked_reads_clear_protected_values() {
        for panic in [false, true] {
            let mut view = populated(Instant::now());
            view.request = Some(tokio::spawn(async move {
                assert!(!panic, "fixture read panic");
                Err(ReadRefusal::Denied)
            }));
            view.complete().await;
            assert!(!view.pending());
            let text = view.text(Instant::now());
            assert!(!text.contains("private-plan"));
            assert!(!text.contains("Peak context tokens: 42"));
            assert!(text.contains("unavailable"));
        }
    }

    // spec: TUI-RUNTIME-R010.9
    #[tokio::test]
    async fn keys_own_one_read_and_close_cancel_and_drop_abort_it() {
        for key in [Some(KeyCode::Esc), Some(KeyCode::Char('c')), None] {
            let mut view = populated(Instant::now());
            let (send, receive) = std::sync::mpsc::channel::<()>();
            view.request = Some(tokio::spawn(async move {
                let _send = send;
                std::future::pending::<()>().await;
                Err(ReadRefusal::Unavailable)
            }));
            let id = view.request.as_ref().unwrap().id();
            assert!(view.key(KeyCode::Char('r'), client()));
            assert!(view.key(KeyCode::Char('i'), client()));
            assert_eq!(view.request.as_ref().unwrap().id(), id);
            assert!(view.key(KeyCode::Char('x'), client()));
            assert!(view.key(KeyCode::Char('y'), client()));
            if let Some(key) = key {
                assert!(view.key(key, client()));
                assert!(!view.pending());
                assert!(!view.text(Instant::now()).contains("private-plan"));
                assert_eq!(view.is_open(), key != KeyCode::Esc);
            } else {
                drop(view);
            }
            assert!(
                tokio::time::timeout(Duration::from_secs(1), async {
                    loop {
                        match receive.try_recv() {
                            Err(std::sync::mpsc::TryRecvError::Disconnected) => break true,
                            Err(std::sync::mpsc::TryRecvError::Empty) => {
                                tokio::task::yield_now().await
                            }
                            Ok(()) => break false,
                        }
                    }
                })
                .await
                .unwrap()
            );
        }
    }

    // spec: TUI-RUNTIME-R010.9
    #[tokio::test]
    async fn opening_without_run_never_starts_a_read() {
        let mut view = InspectorView::default();
        view.task_updated(Some(&binding(None)));
        view.open(client());
        assert!(view.is_open());
        assert!(!view.pending());
        assert!(
            view.text(Instant::now())
                .contains("no validated run binding")
        );
    }

    // spec: TUI-RUNTIME-R010.9
    #[test]
    fn redraw_expires_plan_without_input_or_another_read() {
        let now = Instant::now();
        let mut view = populated(now);
        let mut terminal = Terminal::new(TestBackend::new(120, 20)).unwrap();
        for (at, visible) in [(now, true), (now + Duration::from_secs(2), false)] {
            terminal
                .draw(|frame| view.draw(frame, Style::default(), at))
                .unwrap();
            let text: String = terminal
                .backend()
                .buffer()
                .content()
                .iter()
                .map(|cell| cell.symbol())
                .collect();
            assert_eq!(text.contains("private-plan"), visible);
            assert!(text.contains("Peak context tokens: 42"));
        }
    }
}
