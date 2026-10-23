//! Inline task-bound public folds. Keyboard toggles never perform task actions.
use agent_terminal_ui_native::{
    ArboraClient,
    correlation::TaskCorrelation,
    public_run_events::{MAX_EVENTS, MAX_VIEW_BYTES, PublicEvent, PublicPage},
    run_inspector::ReadRefusal,
};
use crossterm::event::{
    KeyCode, KeyEvent, KeyEventKind, KeyModifiers, MouseButton, MouseEvent, MouseEventKind,
};
use ratatui::{
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
};
use std::{
    collections::{HashSet, VecDeque},
    sync::Arc,
    time::{Duration, Instant},
};
use tokio::task::JoinHandle;

type Read = JoinHandle<Result<PublicPage, ReadRefusal>>;

#[derive(Default)]
pub struct PublicDetailsView {
    binding: Option<TaskCorrelation>,
    choice_binding: Option<TaskCorrelation>,
    request: Option<Read>,
    records: VecDeque<PublicEvent>,
    cursor: u64,
    terminal: bool,
    paused: bool,
    expanded: [bool; 2],
    selected: Option<usize>,
    reveal_selected: bool,
    next_read: Option<Instant>,
    header_regions: [Option<Rect>; 2],
}

impl PublicDetailsView {
    pub fn task_updated(&mut self, binding: Option<&TaskCorrelation>) {
        let valid = binding;
        if self.binding.as_ref() != valid {
            self.abort();
            self.binding = valid.cloned();
            if valid.is_some() && valid != self.choice_binding.as_ref() {
                self.choice_binding = valid.cloned();
                self.expanded = [false; 2];
                self.selected = None;
            }
            self.header_regions = [None; 2];
        }
    }

    pub fn pending(&self) -> bool {
        self.request.is_some()
    }
    pub fn active(&self) -> bool {
        !self.paused
            && self
                .binding
                .as_ref()
                .is_some_and(|binding| binding.run_id().is_some())
            && self.expanded.iter().any(|value| *value)
    }

    pub fn abort(&mut self) {
        if let Some(request) = self.request.take() {
            request.abort();
        }
        self.records.clear();
        self.cursor = 0;
        self.terminal = false;
        self.paused = false;
        self.next_read = None;
    }

    pub fn cancel_read(&mut self) {
        self.abort();
        self.paused = true;
    }

    pub fn replay(&mut self) {
        self.abort();
    }

    pub fn tick(&mut self, client: Arc<ArboraClient>, now: Instant) {
        if !self.active()
            || self.pending()
            || self.terminal
            || self.next_read.is_some_and(|deadline| deadline > now)
        {
            return;
        }
        let Some(binding) = self.binding.as_ref() else {
            return;
        };
        let Some(run) = binding.run_id().map(str::to_owned) else {
            return;
        };
        let task = binding.task_id().to_owned();
        let after = self.cursor;
        self.request = Some(tokio::spawn(async move {
            client.get_public_run_events(&run, &task, after).await
        }));
    }

    fn apply(&mut self, page: PublicPage) {
        let retained_ids: HashSet<_> = self.records.iter().map(|event| &event.event_id).collect();
        if !page.events.is_empty()
            && (self.terminal
                || page.events.first().map(|event| event.sequence) != self.cursor.checked_add(1)
                || page
                    .events
                    .iter()
                    .any(|event| retained_ids.contains(&event.event_id)))
        {
            self.abort();
            self.paused = true;
            return;
        }
        self.records.extend(page.events);
        while self.records.len() > MAX_EVENTS {
            self.records.pop_front();
        }
        let mut retained_bytes: usize = self.records.iter().map(|event| event.text.len()).sum();
        while retained_bytes > MAX_VIEW_BYTES {
            let Some(event) = self.records.pop_front() else {
                break;
            };
            retained_bytes -= event.text.len();
        }
        self.cursor = page.next_after;
        self.terminal = page.terminal;
        self.next_read = if page.has_more {
            None
        } else {
            Some(Instant::now() + Duration::from_secs(1))
        };
    }

    pub async fn complete(&mut self) {
        let Some(request) = self.request.as_mut() else {
            return;
        };
        let result = request.await;
        self.request = None;
        match result {
            Ok(Ok(page)) => self.apply(page),
            Ok(Err(ReadRefusal::Denied | ReadRefusal::WrongRun)) => {
                self.abort();
                self.paused = true;
            }
            _ => {
                self.abort();
                self.next_read = Some(Instant::now() + Duration::from_secs(1));
            }
        }
    }

    fn toggle(&mut self, index: usize) {
        self.selected = Some(index);
        self.paused = false;
        self.expanded[index] = !self.expanded[index];
        if !self.active()
            && let Some(request) = self.request.take()
        {
            request.abort();
        }
    }

    pub fn key(&mut self, key: KeyEvent) -> bool {
        if self.binding.is_none() || key.kind != KeyEventKind::Press {
            return false;
        }
        match (key.code, key.modifiers) {
            (KeyCode::Tab, KeyModifiers::NONE) => {
                self.selected = Some(self.selected.map_or(0, |index| (index + 1) % 2))
            }
            (KeyCode::BackTab, modifiers)
                if modifiers.is_empty() || modifiers == KeyModifiers::SHIFT =>
            {
                self.selected = Some(self.selected.map_or(1, |index| (index + 1) % 2))
            }
            (KeyCode::Enter | KeyCode::Char(' '), KeyModifiers::NONE)
                if self.selected.is_some() =>
            {
                self.toggle(self.selected.unwrap())
            }
            (KeyCode::Esc, KeyModifiers::NONE) if self.selected.is_some() => self.selected = None,
            _ => return false,
        }
        self.reveal_selected = self.selected.is_some();
        true
    }

    pub fn take_focus_request(&mut self) -> Option<usize> {
        if std::mem::take(&mut self.reveal_selected) {
            self.selected
        } else {
            None
        }
    }

    pub fn mouse(&mut self, event: MouseEvent) -> bool {
        if self.binding.is_none()
            || event.kind != MouseEventKind::Down(MouseButton::Left)
            || !event.modifiers.is_empty()
        {
            return false;
        }
        for index in 0..2 {
            if self.header_regions[index]
                .is_some_and(|area| area.contains((event.column, event.row).into()))
            {
                self.toggle(index);
                return true;
            }
        }
        false
    }

    pub fn append_lines(&self, lines: &mut Vec<Line<'static>>, style: Style) -> [Option<usize>; 2] {
        if self.binding.is_none() {
            lines.push(Line::from(
                "Public model summary unavailable: no validated run binding.",
            ));
            lines.push(Line::from(
                "Execution trace unavailable: no validated run binding.",
            ));
            return [None; 2];
        }
        let mut headers = [None; 2];
        for (index, label) in ["Public model summary", "Execution trace"]
            .into_iter()
            .enumerate()
        {
            headers[index] = Some(lines.len());
            let indicator = if self.expanded[index] { "▼" } else { "▶" };
            let focus = if self.selected == Some(index) {
                style.add_modifier(Modifier::REVERSED)
            } else {
                style
            };
            lines.push(Line::from(Span::styled(
                format!("{indicator} {label}"),
                focus,
            )));
            if self.expanded[index] {
                if self
                    .binding
                    .as_ref()
                    .is_none_or(|binding| binding.run_id().is_none())
                {
                    lines.push(Line::from("Unavailable: no validated run binding."));
                    continue;
                }
                let selected: Vec<_> = self
                    .records
                    .iter()
                    .filter(|event| event.summary.is_some() == (index == 0))
                    .collect();
                if selected.is_empty() {
                    lines.push(Line::from(if index == 0 {
                        "Public model summary unavailable: no public summary in the retained event window."
                    } else {
                        "Execution trace unavailable."
                    }));
                } else {
                    if index == 1 && self.records.front().is_some_and(|event| event.sequence > 1) {
                        lines.push(Line::from("Earlier events omitted from this bounded view."));
                    }
                    for event in selected {
                        lines.extend(event.text.lines().map(|line| Line::from(line.to_owned())));
                        lines.push(Line::from(""));
                    }
                }
            }
        }
        headers
    }

    pub fn set_header_regions(&mut self, regions: [Option<Rect>; 2]) {
        self.header_regions = regions;
    }
}

impl Drop for PublicDetailsView {
    fn drop(&mut self) {
        self.abort();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{draw_task_viewport, presentation::Viewport};
    use agent_terminal_ui_native::correlation::TaskCorrelation;
    use ratatui::{Terminal, backend::TestBackend};
    use serde_json::{Value, json};

    fn binding(run: &str) -> TaskCorrelation {
        TaskCorrelation::from_task(&json!({"kind":"task", "id":"task-1", "contextId":"context-1", "status":{"state":"working"}, "metadata":{"arbora":{"runId":run}}})).unwrap()
    }
    fn page() -> PublicPage {
        let value: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/public_run_events.json"
        ))
        .unwrap();
        PublicPage::parse(&value, "run-1", 0).unwrap()
    }
    fn key(code: KeyCode) -> KeyEvent {
        KeyEvent::new(code, KeyModifiers::NONE)
    }
    fn shown(terminal: &Terminal<TestBackend>) -> String {
        terminal
            .backend()
            .buffer()
            .content()
            .iter()
            .map(|cell| cell.symbol())
            .collect()
    }

    // spec: TUI-RUNTIME-R008.2.3.2.2.2.2.2.1
    #[tokio::test]
    async fn wheel_routes_only_to_visible_view_and_preserves_folds() {
        use crate::{HostLogView, InspectorView, route_mouse};
        let mut details = PublicDetailsView::default();
        details.task_updated(Some(&binding("run-1")));
        details.apply(page());
        details.key(key(KeyCode::Tab));
        details.key(key(KeyCode::Enter));
        let folds = details.expanded;
        let selected = details.selected;
        let mut viewport = Viewport::default();
        viewport.measure(100, 5);
        let mut logs = HostLogView::default();
        let mut inspector = InspectorView::default();
        let wheel = MouseEvent {
            kind: MouseEventKind::ScrollDown,
            column: 1,
            row: 1,
            modifiers: KeyModifiers::NONE,
        };
        assert!(route_mouse(
            wheel,
            false,
            &mut logs,
            &mut inspector,
            &mut viewport,
            &mut details
        ));
        assert_eq!(viewport.offset(), 1);
        assert!(!route_mouse(
            wheel,
            true,
            &mut logs,
            &mut inspector,
            &mut viewport,
            &mut details
        ));
        assert_eq!(viewport.offset(), 1);
        let client = Arc::new(ArboraClient::new("http://127.0.0.1:1", None).unwrap());
        inspector.open(client.clone());
        let now = Instant::now();
        let mut terminal = Terminal::new(TestBackend::new(20, 4)).unwrap();
        terminal
            .draw(|frame| inspector.draw(frame, Style::reset(), now))
            .unwrap();
        let inspector_before = shown(&terminal);
        assert!(route_mouse(
            wheel,
            false,
            &mut logs,
            &mut inspector,
            &mut viewport,
            &mut details
        ));
        terminal
            .draw(|frame| inspector.draw(frame, Style::reset(), now))
            .unwrap();
        let inspector_after = shown(&terminal);
        assert_ne!(inspector_before, inspector_after);
        assert_eq!(viewport.offset(), 1);
        logs.open(client);
        terminal
            .draw(|frame| logs.draw(frame, Style::reset()))
            .unwrap();
        let logs_before = shown(&terminal);
        assert!(route_mouse(
            wheel,
            false,
            &mut logs,
            &mut inspector,
            &mut viewport,
            &mut details
        ));
        terminal
            .draw(|frame| logs.draw(frame, Style::reset()))
            .unwrap();
        let logs_after = shown(&terminal);
        assert_ne!(logs_before, logs_after);
        assert_eq!(viewport.offset(), 1);
        terminal
            .draw(|frame| inspector.draw(frame, Style::reset(), now))
            .unwrap();
        assert_eq!(shown(&terminal), inspector_after);
        assert!(!route_mouse(
            wheel,
            true,
            &mut logs,
            &mut inspector,
            &mut viewport,
            &mut details
        ));
        for modifiers in [
            KeyModifiers::CONTROL,
            KeyModifiers::ALT,
            KeyModifiers::SHIFT,
        ] {
            assert!(!route_mouse(
                MouseEvent { modifiers, ..wheel },
                false,
                &mut logs,
                &mut inspector,
                &mut viewport,
                &mut details
            ));
        }
        terminal
            .draw(|frame| logs.draw(frame, Style::reset()))
            .unwrap();
        assert_eq!(shown(&terminal), logs_after);
        logs.close();
        inspector.close();
        assert!(route_mouse(
            wheel,
            false,
            &mut logs,
            &mut inspector,
            &mut viewport,
            &mut details
        ));
        assert_eq!(viewport.offset(), 2);
        assert_eq!(details.expanded, folds);
        assert_eq!(details.selected, selected);
    }

    // spec: TUI-RUNTIME-R008.2.3.2.2.1
    #[test]
    fn actual_task_renderer_starts_collapsed_and_keyboard_choices_survive_updates() {
        let mut view = PublicDetailsView::default();
        view.task_updated(Some(&binding("run-1")));
        view.apply(page());
        let mut terminal = Terminal::new(TestBackend::new(100, 40)).unwrap();
        let mut viewport = Viewport::default();
        terminal
            .draw(|frame| {
                draw_task_viewport(
                    frame,
                    "Task ID: task-1\nReply: visible answer",
                    Style::reset(),
                    &mut viewport,
                    false,
                    &mut view,
                )
            })
            .unwrap();
        assert!(!shown(&terminal).contains("Public explanation:"));
        assert!(shown(&terminal).contains("Reply: visible answer"));
        assert!(view.key(key(KeyCode::Tab)));
        assert!(view.key(key(KeyCode::Enter)));
        view.task_updated(Some(&binding("run-1")));
        terminal
            .draw(|frame| {
                draw_task_viewport(
                    frame,
                    "Task ID: task-1\nReply: visible answer",
                    Style::reset(),
                    &mut viewport,
                    false,
                    &mut view,
                )
            })
            .unwrap();
        assert!(shown(&terminal).contains("Public explanation:"));
        assert!(!shown(&terminal).contains("task_started"));
        assert!(view.key(key(KeyCode::Char(' '))));
        assert!(view.key(key(KeyCode::Tab)));
        assert!(view.key(key(KeyCode::Enter)));
        view.replay();
        view.apply(page());
        assert_eq!(view.expanded, [false, true]);
        terminal
            .draw(|frame| {
                draw_task_viewport(
                    frame,
                    "Task",
                    Style::reset(),
                    &mut viewport,
                    false,
                    &mut view,
                )
            })
            .unwrap();
        assert!(shown(&terminal).contains("task_started"));
        assert!(!shown(&terminal).contains("Public explanation:"));
    }

    // spec: TUI-RUNTIME-R008.2.3.2.2.1
    #[test]
    fn mouse_hit_regions_follow_wrapping_scroll_resize_and_only_left_click_toggles() {
        let mut view = PublicDetailsView::default();
        view.task_updated(Some(&binding("run-1")));
        view.apply(page());
        let mut terminal = Terminal::new(TestBackend::new(40, 20)).unwrap();
        let mut viewport = Viewport::default();
        terminal
            .draw(|frame| {
                draw_task_viewport(
                    frame,
                    "Task text wraps across the narrow terminal before the fold",
                    Style::reset(),
                    &mut viewport,
                    true,
                    &mut view,
                )
            })
            .unwrap();
        let region = view.header_regions[1].unwrap();
        assert!(view.mouse(MouseEvent {
            kind: MouseEventKind::Down(MouseButton::Left),
            column: region.x,
            row: region.y,
            modifiers: KeyModifiers::NONE
        }));
        assert_eq!(view.expanded, [false, true]);
        assert!(!view.mouse(MouseEvent {
            kind: MouseEventKind::Down(MouseButton::Right),
            column: region.x,
            row: region.y,
            modifiers: KeyModifiers::NONE
        }));
        viewport.handle(KeyCode::End);
        terminal
            .draw(|frame| {
                draw_task_viewport(
                    frame,
                    &"long status\n".repeat(30),
                    Style::reset(),
                    &mut viewport,
                    true,
                    &mut view,
                )
            })
            .unwrap();
        assert!(
            view.header_regions
                .iter()
                .all(|region| region.is_none_or(|region| region.y < 19))
        );
    }

    // spec: TUI-RUNTIME-R008.2.3.2.2.1
    #[test]
    fn keyboard_focus_reveals_offscreen_header_without_pinning_later_scroll() {
        let mut view = PublicDetailsView::default();
        view.task_updated(Some(&binding("run-1")));
        let mut terminal = Terminal::new(TestBackend::new(40, 12)).unwrap();
        let mut viewport = Viewport::default();
        let status = "long task output\n".repeat(100);
        terminal
            .draw(|frame| {
                draw_task_viewport(
                    frame,
                    &status,
                    Style::reset(),
                    &mut viewport,
                    false,
                    &mut view,
                )
            })
            .unwrap();
        assert!(view.header_regions[0].is_none());
        assert!(view.key(key(KeyCode::Tab)));
        terminal
            .draw(|frame| {
                draw_task_viewport(
                    frame,
                    &status,
                    Style::reset(),
                    &mut viewport,
                    false,
                    &mut view,
                )
            })
            .unwrap();
        assert!(view.header_regions[0].is_some());
        assert!(shown(&terminal).contains("Public model summary"));
        viewport.handle(KeyCode::Home);
        terminal
            .draw(|frame| {
                draw_task_viewport(
                    frame,
                    &status,
                    Style::reset(),
                    &mut viewport,
                    false,
                    &mut view,
                )
            })
            .unwrap();
        assert_eq!(viewport.offset(), 0);
        assert!(view.header_regions[0].is_none());
    }

    // spec: TUI-RUNTIME-R008.2.3.2.2.1
    #[test]
    fn modified_repeat_release_and_effect_keys_are_not_fold_actions() {
        let mut view = PublicDetailsView::default();
        view.task_updated(Some(&binding("run-1")));
        for code in [
            KeyCode::Char('x'),
            KeyCode::Char('y'),
            KeyCode::Char('c'),
            KeyCode::Char('q'),
            KeyCode::Char('r'),
            KeyCode::Enter,
            KeyCode::Char(' '),
        ] {
            assert!(!view.key(key(code)));
        }
        assert!(view.key(key(KeyCode::Tab)));
        for kind in [KeyEventKind::Repeat, KeyEventKind::Release] {
            assert!(!view.key(KeyEvent {
                kind,
                ..key(KeyCode::Enter)
            }));
        }
        assert!(!view.key(KeyEvent::new(KeyCode::Enter, KeyModifiers::CONTROL)));
        assert_eq!(view.expanded, [false; 2]);
    }

    // spec: TUI-RUNTIME-R008.2.3.2.2.1
    #[test]
    fn task_without_run_has_keyboard_folds_but_never_reads() {
        let task = TaskCorrelation::from_task(&json!({"kind":"task", "id":"task-1", "contextId":"context-1", "status":{"state":"working"}})).unwrap();
        let mut view = PublicDetailsView::default();
        view.task_updated(Some(&task));
        assert!(view.key(key(KeyCode::Tab)));
        assert!(view.key(key(KeyCode::Enter)));
        assert!(!view.active() && !view.pending());
        view.task_updated(Some(&task));
        view.replay();
        assert_eq!(view.expanded, [true, false]);
        let mut lines = Vec::new();
        assert_eq!(
            view.append_lines(&mut lines, Style::reset()),
            [Some(0), Some(2)]
        );
        let content = lines
            .iter()
            .map(ToString::to_string)
            .collect::<Vec<_>>()
            .join("\n");
        assert!(content.contains("▼ Public model summary"));
        assert!(content.contains("▶ Execution trace"));
        assert!(content.contains("Unavailable: no validated run binding."));
    }

    // spec: TUI-RUNTIME-R008.2.3.2.2.1
    #[test]
    fn duplicate_identity_across_pages_clears_values_and_preserves_folds() {
        let mut view = PublicDetailsView::default();
        view.task_updated(Some(&binding("run-1")));
        view.expanded = [true, false];
        let mut first = page();
        first.events.truncate(2);
        first.next_after = 2;
        first.terminal = false;
        view.apply(first);
        let mut second = page();
        second.events.drain(..2);
        second.events[0].event_id = view.records[0].event_id.clone();
        view.apply(second);
        assert!(view.records.is_empty());
        assert!(!view.active());
        assert_eq!(view.expanded, [true, false]);
    }

    // spec: TUI-RUNTIME-R008.2.3.2.2.1
    #[test]
    fn retained_display_text_is_bounded_even_across_large_pages() {
        let mut view = PublicDetailsView::default();
        view.task_updated(Some(&binding("run-1")));
        let events = (1..=1000)
            .map(|sequence| PublicEvent {
                event_id: sequence.to_string(),
                sequence,
                summary: Some("x".repeat(16_384)),
                text: "x".repeat(16_384),
                terminal: false,
            })
            .collect();
        view.apply(PublicPage {
            events,
            next_after: 1000,
            has_more: false,
            terminal: false,
        });
        assert_eq!(view.records.len(), 8);
        assert_eq!(
            view.records
                .iter()
                .map(|event| event.text.len())
                .sum::<usize>(),
            MAX_VIEW_BYTES
        );
        assert_eq!(view.cursor, 1000);
    }

    // spec: TUI-RUNTIME-R008.2.3.2.2.1
    #[tokio::test]
    async fn refusal_and_identity_changes_clear_values_and_abort_pending_reads() {
        let mut view = PublicDetailsView::default();
        view.task_updated(Some(&binding("run-1")));
        view.apply(page());
        view.expanded = [true, false];
        view.request = Some(tokio::spawn(async { Err(ReadRefusal::Denied) }));
        view.complete().await;
        assert!(view.records.is_empty());
        assert!(!view.active());
        assert_eq!(view.expanded, [true, false]);
        view.task_updated(None);
        view.task_updated(Some(&binding("run-1")));
        assert_eq!(view.expanded, [true, false]);
        assert!(view.active());
        view.cancel_read();
        assert!(!view.active());
        view.replay();
        assert!(view.active());
        let request = tokio::spawn(async { std::future::pending().await });
        let abort = request.abort_handle();
        view.request = Some(request);
        view.task_updated(Some(&binding("other-run")));
        tokio::task::yield_now().await;
        assert!(abort.is_finished());
        assert_eq!(view.expanded, [false; 2]);
        assert!(!view.pending());
    }
}
