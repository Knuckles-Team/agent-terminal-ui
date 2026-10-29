use crate::{
    presentation::Viewport,
    spatial_graph::{SpatialGraph, label},
};
use agent_terminal_ui_native::{
    ArboraClient,
    correlation::TaskCorrelation,
    execution_graph::ExecutionGraph,
    run_inspector::{ReadRefusal, RunInspector},
    run_inspector_client::RunRead,
};
use crossterm::event::{KeyCode, KeyEvent, KeyEventKind, KeyModifiers, MouseEvent};
use ratatui::{
    Frame,
    layout::Rect,
    style::{Modifier, Style},
    text::Line,
    widgets::{Block, Paragraph, Wrap},
};
use std::{sync::Arc, time::Instant};
use tokio::task::JoinHandle;

type ReadTask = JoinHandle<Result<RunRead, ReadRefusal>>;
type GraphReadTask = JoinHandle<(GraphScope, Result<ExecutionGraph, ReadRefusal>)>;

struct GraphScope {
    binding: TaskCorrelation,
    client: Arc<ArboraClient>,
    generation: u64,
}

#[derive(Default)]
pub struct InspectorView {
    binding: Option<TaskCorrelation>,
    inspector: Option<RunInspector>,
    request: Option<ReadTask>,
    graph_request: Option<GraphReadTask>,
    client: Option<Arc<ArboraClient>>,
    generation: u64,
    graph_mode: bool,
    graph: Option<ExecutionGraph>,
    spatial: Option<SpatialGraph>,
    spatial_mode: bool,
    spatial_visible: bool,
    graph_refusal: Option<ReadRefusal>,
    selected_step: Option<usize>,
    reveal_step: bool,
    open: bool,
    viewport: Viewport,
    search: Option<InspectorSearch>,
}

#[derive(Default)]
struct InspectorSearch {
    query: String,
    selected: usize,
    matches: usize,
    reveal: bool,
}

impl InspectorSearch {
    fn edit(&mut self, key: KeyEvent) {
        match (key.code, key.modifiers) {
            (KeyCode::Enter, modifiers)
                if self.matches > 0
                    && (modifiers.is_empty() || modifiers == KeyModifiers::SHIFT) =>
            {
                let step = if modifiers == KeyModifiers::SHIFT {
                    self.matches - 1
                } else {
                    1
                };
                self.selected = (self.selected + step) % self.matches;
            }
            (KeyCode::Backspace, KeyModifiers::NONE) => {
                self.query.pop();
                self.selected = 0;
            }
            (KeyCode::Char(ch), modifiers)
                if (modifiers.is_empty() || modifiers == KeyModifiers::SHIFT)
                    && !ch.is_control()
                    && self.query.chars().count() < 128 =>
            {
                self.query.push(ch);
                self.selected = 0;
            }
            _ => return,
        }
        self.reveal = true;
    }

    fn lines<'a>(&mut self, text: &'a str) -> (Vec<Line<'a>>, Option<usize>) {
        let query = self.query.to_lowercase();
        let matching: Vec<_> = text
            .lines()
            .enumerate()
            .filter(|(_, line)| !query.is_empty() && line.to_lowercase().contains(&query))
            .map(|(index, _)| index)
            .collect();
        self.matches = matching.len();
        self.selected = self.selected.min(self.matches.saturating_sub(1));
        let selected = matching.get(self.selected).copied();
        let lines = text
            .lines()
            .enumerate()
            .map(|(index, line)| {
                let line = Line::from(line);
                if Some(index) == selected {
                    line.style(Style::new().add_modifier(Modifier::REVERSED))
                } else {
                    line
                }
            })
            .collect();
        (lines, selected)
    }

    fn title(&self) -> String {
        let position = if self.matches == 0 {
            0
        } else {
            self.selected + 1
        };
        format!(
            "Find: {} [{position}/{}] Enter: next Shift+Enter: previous Esc: close",
            self.query, self.matches
        )
    }
}

impl InspectorView {
    pub fn is_open(&self) -> bool {
        self.open
    }
    pub fn pending(&self) -> bool {
        self.request.is_some() || self.graph_request.is_some()
    }

    /// Only a successful, correlated task read may select a run.
    pub fn task_updated(&mut self, binding: Option<&TaskCorrelation>) {
        let run = binding.and_then(TaskCorrelation::run_id);
        if binding != self.binding.as_ref() || binding.is_none() {
            self.abort();
            self.binding = binding.cloned();
            self.inspector = run.map(|run| RunInspector::new(run.to_owned()));
            self.viewport = Viewport::default();
            self.search = None;
        }
    }

    /// An immutable client owns endpoint and credential identity for the read.
    pub fn client_updated(&mut self, client: &Arc<ArboraClient>) {
        if self
            .client
            .as_ref()
            .is_some_and(|current| !Arc::ptr_eq(current, client))
        {
            self.abort();
            self.search = None;
            self.viewport = Viewport::default();
        }
        self.client = Some(client.clone());
    }

    pub fn open(&mut self, client: Arc<ArboraClient>) {
        self.open = true;
        self.refresh(client);
    }

    fn refresh(&mut self, client: Arc<ArboraClient>) {
        self.client_updated(&client);
        if self.graph_mode {
            self.abort();
            let Some(binding) = self
                .binding
                .clone()
                .filter(|binding| binding.run_id().is_some())
            else {
                return;
            };
            let scope = GraphScope {
                binding,
                client: client.clone(),
                generation: self.generation,
            };
            self.graph_request = Some(tokio::spawn(async move {
                let result = client.get_execution_graph(&scope.binding).await;
                (scope, result)
            }));
            return;
        }
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
        self.graph = None;
        self.spatial = None;
        self.spatial_visible = false;
        self.selected_step = None;
        self.reveal_step = false;
        self.graph_refusal = None;
        if let Some(inspector) = &mut self.inspector {
            let _ = inspector.accept_read(Err(ReadRefusal::Unavailable), Instant::now());
        }
    }

    fn abort(&mut self) {
        self.generation = self.generation.wrapping_add(1);
        if let Some(request) = self.graph_request.take() {
            request.abort();
        }
        if let Some(request) = self.request.take() {
            request.abort();
        }
        self.clear_read();
    }

    pub fn close(&mut self) {
        self.abort();
        self.open = false;
        self.graph_mode = false;
        self.spatial_mode = false;
        self.search = None;
    }

    pub async fn complete(&mut self) {
        if let Some(request) = self.graph_request.as_mut() {
            let reply = request.await;
            self.graph_request = None;
            self.clear_read();
            if let Ok((scope, result)) = reply
                && self.open
                && self.graph_mode
                && scope.generation == self.generation
                && self.binding.as_ref() == Some(&scope.binding)
                && self
                    .client
                    .as_ref()
                    .is_some_and(|client| Arc::ptr_eq(client, &scope.client))
            {
                match result {
                    Ok(graph) => {
                        self.spatial = Some(SpatialGraph::new(&graph));
                        self.graph = Some(graph);
                        self.selected_step = Some(0);
                        self.reveal_step = true;
                    }
                    Err(error) => self.graph_refusal = Some(error),
                }
            }
            return;
        }
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
        self.client_updated(&client);
        match key {
            KeyCode::Esc => self.close(),
            KeyCode::Char('g') => {
                self.abort();
                self.graph_mode = !self.graph_mode;
                self.search = None;
                self.viewport = Viewport::default();
                self.refresh(client);
            }
            KeyCode::Char('v') if self.graph_mode => {
                self.spatial_mode = !self.spatial_mode;
            }
            KeyCode::Tab | KeyCode::BackTab if self.graph_mode => {
                if let Some(graph) = &self.graph {
                    let step = if key == KeyCode::BackTab {
                        graph.nodes.len() - 1
                    } else {
                        1
                    };
                    self.selected_step =
                        Some((self.selected_step.unwrap_or(0) + step) % graph.nodes.len());
                    self.reveal_step = true;
                    if let Some(spatial) = &mut self.spatial {
                        spatial.focus_selected();
                    }
                }
            }
            KeyCode::Char('c') => self.abort(),
            KeyCode::Char('r') | KeyCode::Char('i') => self.refresh(client),
            _ if self.spatial_mode && self.spatial_visible && self.search.is_none() => {
                if let Some(spatial) = &mut self.spatial {
                    spatial.key(key);
                }
            }
            _ => {
                self.viewport.handle(key);
            }
        }
        true
    }

    /// Search owns typed characters before the application's action shortcuts.
    pub fn search_key(&mut self, key: KeyEvent) -> bool {
        if !self.open
            || key.kind != KeyEventKind::Press
            || (key.code == KeyCode::Char('c') && key.modifiers == KeyModifiers::CONTROL)
        {
            return false;
        }
        if key.code == KeyCode::Char('f') && key.modifiers == KeyModifiers::CONTROL {
            self.search.get_or_insert_with(InspectorSearch::default);
            return true;
        }
        let Some(search) = &mut self.search else {
            return false;
        };
        if key.code == KeyCode::Esc && key.modifiers.is_empty() {
            self.search = None;
        } else {
            search.edit(key);
        }
        true
    }

    fn text(&mut self, now: Instant) -> String {
        let body = if self.graph_mode {
            match &self.graph {
                Some(graph) => graph.text(self.selected_step.unwrap_or(0)),
                None if self
                    .binding
                    .as_ref()
                    .and_then(TaskCorrelation::run_id)
                    .is_none() =>
                {
                    "Execution graph unavailable: no validated run binding".to_owned()
                }
                None if self.graph_refusal == Some(ReadRefusal::Denied) => {
                    "Execution graph denied; protected data cleared".to_owned()
                }
                None => "Execution graph unavailable".to_owned(),
            }
        } else {
            match &mut self.inspector {
                Some(inspector) => inspector.text(now),
                None => "Run inspector unavailable: no validated run binding".to_owned(),
            }
        };
        let state = if self.pending() {
            if self.graph_mode {
                "Reading execution graph...\n"
            } else {
                "Reading run...\n"
            }
        } else {
            ""
        };
        let map_help = if self.graph_mode {
            "v: map / full list and details\n"
        } else {
            ""
        };
        format!(
            "{state}{body}\n\n{map_help}g: graph / summary\nr / i: refresh | c: cancel local read\nEscape: close | q: quit"
        )
    }

    pub fn mouse(&mut self, event: MouseEvent) -> bool {
        if self.open && self.spatial_mode && self.spatial_visible && self.search.is_none() {
            if event.modifiers.is_empty()
                && let Some(spatial) = &mut self.spatial
            {
                match event.kind {
                    crossterm::event::MouseEventKind::ScrollUp => spatial.key(KeyCode::Up),
                    crossterm::event::MouseEventKind::ScrollDown => spatial.key(KeyCode::Down),
                    _ => return false,
                }
                return true;
            }
            return false;
        }
        self.open && self.viewport.mouse(event)
    }

    fn draw_spatial(&mut self, frame: &mut Frame, style: Style, border_style: Style) {
        let (Some(graph), Some(spatial)) = (&self.graph, &mut self.spatial) else {
            return;
        };
        let selected = self.selected_step.unwrap_or(0);
        let outer = Block::bordered()
            .border_style(border_style)
            .title_style(border_style)
            .title("Flat execution DAG (read-only; selected edges)")
            .title_bottom("v: full list/details | Ctrl+F: find | g: summary | Esc: close");
        let inner = outer.inner(frame.area());
        frame.render_widget(outer.style(style), frame.area());
        let header = format!(
            "Run: {}
Plan-step depends_on: predecessor -> dependent; selected edges only
Lifecycle: incomplete; observed prefix only
Arrows: pan | Tab/Shift+Tab: select | Home: focus | F6: theme",
            label(&graph.run_id)
        );
        frame.render_widget(
            Paragraph::new(header).style(style),
            Rect::new(inner.x, inner.y, inner.width, 4),
        );
        let map_area = Rect::new(inner.x, inner.y + 4, inner.width, inner.height - 9);
        spatial.draw(frame, map_area, graph, selected, style);
        let adjacent = |incoming| {
            let nodes: Vec<_> = graph
                .edges
                .iter()
                .filter_map(|&(from, to)| {
                    if incoming && to == selected {
                        Some(from + 1)
                    } else if !incoming && from == selected {
                        Some(to + 1)
                    } else {
                        None
                    }
                })
                .map(|i| i.to_string())
                .collect();
            if nodes.is_empty() {
                "none".to_owned()
            } else {
                nodes.join(", ")
            }
        };
        let node = &graph.nodes[selected];
        let details = format!(
            "Selected {}: {} [{}]
Predecessors: {} | Dependents: {}
Public event evidence: {}
Child actions unavailable | unobserved means unknown
r / i: refresh | c: cancel local read | q: quit",
            selected + 1,
            label(&node.task_id),
            node.status,
            adjacent(true),
            adjacent(false),
            node.evidence.as_ref().map_or_else(
                || "unavailable".to_owned(),
                |e| format!("{} (sequence {})", label(&e.event_id), e.sequence)
            )
        );
        frame.render_widget(
            Paragraph::new(details).style(style),
            Rect::new(inner.x, map_area.bottom(), inner.width, 5),
        );
    }

    pub fn draw(&mut self, frame: &mut Frame, style: Style, border_style: Style, now: Instant) {
        self.spatial_visible = self.spatial_mode
            && self.graph_mode
            && self.graph.is_some()
            && self.spatial.is_some()
            && self.search.is_none()
            && frame.area().width >= 72
            && frame.area().height >= 20;
        if self.spatial_visible {
            self.draw_spatial(frame, style, border_style);
            return;
        }
        let mut text = self.text(now);
        if self.spatial_mode && self.graph.is_some() && self.search.is_none() {
            text.insert_str(0, "Map needs 72x20; showing the full list.\n");
        }
        let graph_row = if self.graph_mode {
            text.lines().position(|line| line.starts_with("> "))
        } else {
            None
        };
        let (lines, selected) = match &mut self.search {
            Some(search) => search.lines(&text),
            None => (
                text.lines()
                    .enumerate()
                    .map(|(index, line)| {
                        let line = Line::from(line);
                        if Some(index) == graph_row {
                            line.style(Style::new().add_modifier(Modifier::REVERSED))
                        } else {
                            line
                        }
                    })
                    .collect(),
                None,
            ),
        };
        let title = self
            .search
            .as_ref()
            .map(InspectorSearch::title)
            .unwrap_or_else(|| "Ctrl+F: find | PgUp/PgDn Home/End".to_owned());
        let block = Block::bordered()
            .border_style(border_style)
            .title_style(border_style)
            .title("Run inspector (read-only)")
            .title_bottom(title);
        let inner = block.inner(frame.area());
        let paragraph = Paragraph::new(lines.clone())
            .style(style)
            .wrap(Wrap { trim: false });
        self.viewport
            .measure(paragraph.line_count(inner.width), inner.height);
        if let Some(search) = &mut self.search
            && std::mem::take(&mut search.reveal)
            && let Some(index) = selected
        {
            let row = if index == 0 {
                0
            } else {
                Paragraph::new(lines[..index].to_vec())
                    .wrap(Wrap { trim: false })
                    .line_count(inner.width)
            };
            self.viewport.reveal(row, 1);
        }
        if std::mem::take(&mut self.reveal_step)
            && self.search.is_none()
            && let Some(index) = graph_row
        {
            let row = Paragraph::new(lines[..index].to_vec())
                .wrap(Wrap { trim: false })
                .line_count(inner.width);
            self.viewport.reveal(row, 1);
        }
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
                    summary_available: true,
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

    fn search_text(view: &mut InspectorView, value: &str) {
        assert!(view.search_key(KeyEvent::new(KeyCode::Char('f'), KeyModifiers::CONTROL)));
        for ch in value.chars() {
            assert!(view.search_key(KeyEvent::new(KeyCode::Char(ch), KeyModifiers::NONE)));
        }
    }

    // spec: TUIG-RUNTIME-R010.10
    #[test]
    fn inspector_search_reveals_matches_and_preserves_read_only_actions() {
        let now = Instant::now();
        let mut view = populated(now);
        let mut terminal = Terminal::new(TestBackend::new(50, 6)).unwrap();
        search_text(&mut view, "PRIVATE-PLAN");
        terminal
            .draw(|frame| view.draw(frame, Style::reset(), Style::reset(), now))
            .unwrap();
        assert_eq!(view.search.as_ref().unwrap().matches, 1);
        assert!(view.viewport.offset() > 0);
        assert!(
            terminal
                .backend()
                .buffer()
                .content()
                .iter()
                .any(|cell| cell.modifier.contains(Modifier::REVERSED))
        );
        assert!(!view.pending());
        for ch in ['q', 'r', 'i', 'c', 'x', 'y'] {
            assert!(view.search_key(KeyEvent::new(KeyCode::Char(ch), KeyModifiers::NONE)));
        }
        assert!(view.is_open());
        assert!(!view.pending());
        assert!(view.text(now).contains("private-plan"));
        assert!(!view.search_key(KeyEvent::new(KeyCode::Char('c'), KeyModifiers::CONTROL)));
        assert!(view.search_key(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE)));
        assert!(view.search.is_none());
        assert!(view.is_open());
        assert!(view.key(KeyCode::Esc, client()));
        assert!(!view.is_open());
    }

    // spec: TUIG-RUNTIME-R010.10
    #[test]
    fn search_cycles_unicode_lines_and_bounds_input() {
        let mut search = InspectorSearch::default();
        for ch in "界".chars() {
            search.edit(KeyEvent::new(KeyCode::Char(ch), KeyModifiers::NONE));
        }
        assert_eq!(
            search
                .lines(
                    "first 界
other
last 界"
                )
                .1,
            Some(0)
        );
        search.edit(KeyEvent::new(KeyCode::Enter, KeyModifiers::SHIFT));
        assert_eq!(
            search
                .lines(
                    "first 界
other
last 界"
                )
                .1,
            Some(2)
        );
        search.edit(KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE));
        assert_eq!(
            search
                .lines(
                    "first 界
other
last 界"
                )
                .1,
            Some(0)
        );
        search.edit(KeyEvent::new(KeyCode::Enter, KeyModifiers::CONTROL));
        assert_eq!(search.selected, 0);
        assert_eq!(search.lines("gone").1, None);
        assert!(search.title().contains("[0/0]"));
        search.edit(KeyEvent::new(KeyCode::Backspace, KeyModifiers::NONE));
        assert!(search.query.is_empty());
        for _ in 0..140 {
            search.edit(KeyEvent::new(KeyCode::Char('界'), KeyModifiers::NONE));
        }
        assert_eq!(search.query.chars().count(), 128);
    }

    // spec: TUIG-RUNTIME-R010.10
    #[test]
    fn search_recomputes_after_expiry_refusal_resize_and_run_change() {
        let now = Instant::now();
        let mut view = populated(now);
        let mut terminal = Terminal::new(TestBackend::new(40, 6)).unwrap();
        search_text(&mut view, "private-plan");
        terminal
            .draw(|frame| view.draw(frame, Style::reset(), Style::reset(), now))
            .unwrap();
        assert_eq!(view.search.as_ref().unwrap().matches, 1);
        terminal.backend_mut().resize(30, 8);
        terminal
            .draw(|frame| view.draw(frame, Style::reset(), Style::reset(), now))
            .unwrap();
        assert_eq!(view.search.as_ref().unwrap().matches, 1);
        terminal
            .draw(|frame| {
                view.draw(
                    frame,
                    Style::reset(),
                    Style::reset(),
                    now + Duration::from_secs(2),
                )
            })
            .unwrap();
        assert_eq!(view.search.as_ref().unwrap().matches, 0);
        view.clear_read();
        terminal
            .draw(|frame| view.draw(frame, Style::reset(), Style::reset(), now))
            .unwrap();
        assert_eq!(view.search.as_ref().unwrap().matches, 0);
        view.task_updated(Some(&binding(Some("new-run"))));
        assert!(view.search.is_none());
        search_text(&mut view, "q");
        assert!(!view.search_key(KeyEvent::new_with_kind(
            KeyCode::Char('q'),
            KeyModifiers::NONE,
            KeyEventKind::Release
        )));
        view.close();
        assert!(view.search.is_none());
        assert!(!view.search_key(KeyEvent::new(KeyCode::Char('f'), KeyModifiers::CONTROL)));
    }

    // spec: TUIG-RUNTIME-R010.9
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

    // spec: TUIG-RUNTIME-R008.2.3.2.2.1
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

    // spec: TUIG-RUNTIME-R010.9
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

    // spec: TUIG-RUNTIME-R010.9
    #[tokio::test]
    async fn keys_own_one_read_and_close_cancel_and_drop_abort_it() {
        for key in [Some(KeyCode::Esc), Some(KeyCode::Char('c')), None] {
            let mut view = populated(Instant::now());
            let client = client();
            let (send, receive) = std::sync::mpsc::channel::<()>();
            view.request = Some(tokio::spawn(async move {
                let _send = send;
                std::future::pending::<()>().await;
                Err(ReadRefusal::Unavailable)
            }));
            let id = view.request.as_ref().unwrap().id();
            assert!(view.key(KeyCode::Char('r'), client.clone()));
            assert!(view.key(KeyCode::Char('i'), client.clone()));
            assert_eq!(view.request.as_ref().unwrap().id(), id);
            assert!(view.key(KeyCode::Char('x'), client.clone()));
            assert!(view.key(KeyCode::Char('y'), client.clone()));
            if let Some(key) = key {
                assert!(view.key(key, client.clone()));
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

    // spec: TUIG-RUNTIME-R010.9
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

    // spec: TUIG-RUNTIME-R010.9
    #[test]
    fn redraw_expires_plan_without_input_or_another_read() {
        let now = Instant::now();
        let mut view = populated(now);
        let mut terminal = Terminal::new(TestBackend::new(120, 20)).unwrap();
        for (at, visible) in [(now, true), (now + Duration::from_secs(2), false)] {
            terminal
                .draw(|frame| view.draw(frame, Style::default(), Style::default(), at))
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

    fn graph_view() -> InspectorView {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../tests/fixtures/execution_graph_contract.json"
        ))
        .unwrap();
        let value = &fixture["value"];
        let binding = TaskCorrelation::from_task(
            &json!({"kind":"task", "id":value["task_id"], "contextId":"context-one",
            "status":{"state":"working"}, "metadata":{"arbora":{"runId":value["run_id"]}}}),
        )
        .unwrap();
        let mut view = InspectorView::default();
        view.task_updated(Some(&binding));
        view.client_updated(&client());
        view.open = true;
        view.graph_mode = true;
        let graph = ExecutionGraph::decode(value, &binding).unwrap();
        view.spatial = Some(SpatialGraph::new(&graph));
        view.graph = Some(graph);
        view.selected_step = Some(0);
        view.reveal_step = true;
        view
    }

    fn rendered(terminal: &Terminal<TestBackend>) -> String {
        terminal
            .backend()
            .buffer()
            .content()
            .iter()
            .map(|cell| cell.symbol())
            .collect()
    }

    // spec: TUIG-RUNTIME-R010.12.1, TUIG-RUNTIME-R010.12.1.1, TUIG-RUNTIME-R008.3
    // spec: TUIG-RUNTIME-R010.12.1.2
    #[test]
    fn spatial_map_keeps_selection_and_list_search_across_resize_and_themes() {
        let mut view = graph_view();
        let client = view.client.as_ref().unwrap().clone();
        let now = Instant::now();
        let mut terminal = Terminal::new(TestBackend::new(100, 30)).unwrap();
        assert!(!view.spatial_mode);
        view.key(KeyCode::Char('v'), client.clone());
        for no_color in ["", "1", "0", "false"] {
            let themes = crate::presentation::ThemeSelection::new("canopy", no_color);
            terminal
                .draw(|f| view.draw(f, themes.style(), themes.border_style(), now))
                .unwrap();
            let buffer = terminal.backend().buffer();
            let color = |value| {
                if no_color.is_empty() {
                    ratatui::style::Color::from_u32(value)
                } else {
                    ratatui::style::Color::Reset
                }
            };
            for position in [(0, 0), (1, 0)] {
                assert_eq!(buffer[position].fg, color(0xadc99f));
                assert_eq!(buffer[position].bg, color(0x121c17));
                assert_ne!(buffer[position].symbol(), " ");
            }
            assert_eq!(buffer[(1, 1)].fg, color(0xf1f5eb));
            assert_eq!(buffer[(1, 1)].bg, color(0x121c17));
            assert_eq!(buffer[(1, 1)].symbol(), "R");
            if !no_color.is_empty() {
                assert!(buffer.content().iter().all(|cell| {
                    cell.fg == ratatui::style::Color::Reset
                        && cell.bg == ratatui::style::Color::Reset
                }));
            }
        }
        assert!(view.spatial_visible);
        assert!(
            rendered(&terminal)
                .contains("Plan-step depends_on: predecessor -> dependent; selected edges only")
        );
        assert!(rendered(&terminal).contains("Selected 1: first [running]"));
        assert!(rendered(&terminal).contains("unobserved means unknown"));
        view.key(KeyCode::BackTab, client.clone());
        terminal
            .draw(|f| view.draw(f, Style::reset(), Style::reset(), now))
            .unwrap();
        assert_eq!(view.selected_step, Some(3));
        assert!(rendered(&terminal).contains("Predecessors: 2, 3 | Dependents: none"));
        let map = terminal.backend().buffer().clone();
        for key in [
            KeyCode::Char('x'),
            KeyCode::Char('y'),
            KeyCode::Enter,
            KeyCode::Char(' '),
        ] {
            assert!(view.key(key, client.clone()));
            assert!(!view.pending());
        }
        terminal
            .draw(|f| view.draw(f, Style::reset(), Style::reset(), now))
            .unwrap();
        assert_eq!(&map, terminal.backend().buffer());
        search_text(&mut view, "Predecessors");
        terminal
            .draw(|f| view.draw(f, Style::reset(), Style::reset(), now))
            .unwrap();
        assert!(!view.spatial_visible);
        assert_eq!(view.search.as_ref().unwrap().matches, 1);
        assert!(rendered(&terminal).contains("Predecessors (depends_on): 2: left, 3: right"));
        assert_eq!(view.selected_step, Some(3));
        view.search_key(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE));
        for (width, height, spatial) in [
            (40, 16, false),
            (100, 30, true),
            (80, 10, false),
            (80, 24, true),
        ] {
            terminal.backend_mut().resize(width, height);
            view.reveal_step = true;
            terminal
                .draw(|f| view.draw(f, Style::reset(), Style::reset(), now))
                .unwrap();
            assert_eq!(view.spatial_visible, spatial);
            assert_eq!(view.selected_step, Some(3));
            assert!(rendered(&terminal).contains(if spatial {
                "Selected 4: join"
            } else {
                "4. join [unobserved]"
            }));
        }
        view.key(KeyCode::Char('v'), client.clone());
        terminal
            .draw(|f| view.draw(f, Style::reset(), Style::reset(), now))
            .unwrap();
        assert!(!view.spatial_visible);
        assert!(view.text(now).contains("Message active child: unavailable"));
        view.key(KeyCode::Esc, client);
        assert!(view.spatial.is_none());
        assert!(!view.spatial_mode);
    }

    // spec: TUIG-RUNTIME-R010.12
    #[test]
    fn graph_keyboard_narrow_resize_search_and_edges_keep_one_step_row() {
        let mut view = graph_view();
        let client = view.client.as_ref().unwrap().clone();
        let now = Instant::now();
        let mut terminal = Terminal::new(TestBackend::new(40, 16)).unwrap();
        terminal
            .draw(|frame| view.draw(frame, Style::reset(), Style::reset(), now))
            .unwrap();
        assert!(rendered(&terminal).contains("1. first [running]"));
        assert!(view.key(KeyCode::BackTab, client.clone()));
        terminal
            .draw(|frame| view.draw(frame, Style::reset(), Style::reset(), now))
            .unwrap();
        assert_eq!(view.selected_step, Some(3));
        assert!(rendered(&terminal).contains("4. join [unobserved]"));
        assert_eq!(view.text(now).matches("4. join [unobserved]").count(), 1);
        assert!(
            view.text(now)
                .contains("Predecessors (depends_on): 2: left, 3: right")
        );
        for (width, height) in [(100, 30), (40, 12), (60, 18)] {
            terminal.backend_mut().resize(width, height);
            terminal
                .draw(|frame| view.draw(frame, Style::reset(), Style::reset(), now))
                .unwrap();
            assert_eq!(view.selected_step, Some(3));
        }
        assert!(view.key(KeyCode::Tab, client.clone()));
        assert_eq!(view.selected_step, Some(0));
        search_text(&mut view, "event-2");
        terminal
            .draw(|frame| view.draw(frame, Style::reset(), Style::reset(), now))
            .unwrap();
        assert_eq!(view.search.as_ref().unwrap().matches, 1);
        assert!(rendered(&terminal).contains("event-2"));
        for ch in ['g', 'r', 'c'] {
            assert!(view.search_key(KeyEvent::new(KeyCode::Char(ch), KeyModifiers::NONE)));
        }
        assert!(view.graph.is_some());
        assert!(!view.pending());
        assert!(view.search_key(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE)));
        terminal.backend_mut().resize(40, 16);
        terminal
            .draw(|frame| view.draw(frame, Style::reset(), Style::reset(), now))
            .unwrap();
        assert!(view.key(KeyCode::End, client));
        terminal
            .draw(|frame| view.draw(frame, Style::reset(), Style::reset(), now))
            .unwrap();
        let text = rendered(&terminal);
        assert!(text.contains("Escape: close | q: quit"));
        assert!(text.contains("g: graph / summary"));
    }

    // spec: TUIG-RUNTIME-R010.11, TUIG-RUNTIME-R010.12
    #[tokio::test]
    async fn graph_refresh_cancels_previous_read_and_clears_selection() {
        let mut view = graph_view();
        let client = view.client.as_ref().unwrap().clone();
        view.selected_step = Some(3);
        let (send, receive) = std::sync::mpsc::channel::<()>();
        let scope = GraphScope {
            binding: view.binding.clone().unwrap(),
            client: client.clone(),
            generation: view.generation,
        };
        view.graph_request = Some(tokio::spawn(async move {
            let _send = send;
            std::future::pending::<()>().await;
            (scope, Err(ReadRefusal::Unavailable))
        }));
        let previous = view.graph_request.as_ref().unwrap().id();
        assert!(view.key(KeyCode::Char('r'), client.clone()));
        assert!(view.pending());
        assert_ne!(view.graph_request.as_ref().unwrap().id(), previous);
        assert!(view.graph.is_none());
        assert!(view.spatial.is_none());
        assert!(!view.spatial_visible);
        assert!(view.selected_step.is_none());
        tokio::time::timeout(Duration::from_secs(1), async {
            while matches!(
                receive.try_recv(),
                Err(std::sync::mpsc::TryRecvError::Empty)
            ) {
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap();
        assert!(matches!(
            receive.try_recv(),
            Err(std::sync::mpsc::TryRecvError::Disconnected)
        ));
        assert!(view.key(KeyCode::Char('c'), client));
        assert!(!view.pending());
        assert!(view.graph.is_none());
        assert!(view.spatial.is_none());
        assert!(!view.spatial_visible);
        assert!(view.selected_step.is_none());
    }

    // spec: TUIG-RUNTIME-R010.11
    #[tokio::test]
    async fn graph_is_independent_of_run_summary_and_switches_one_read() {
        let mut view = graph_view();
        let client = view.client.as_ref().unwrap().clone();
        assert!(view.key(KeyCode::Char('g'), client.clone()));
        assert!(!view.graph_mode);
        assert!(view.graph.is_none());
        assert!(view.spatial.is_none());
        assert!(!view.spatial_visible);
        view.complete().await;
        assert!(view.text(Instant::now()).contains("unavailable"));
        assert!(view.key(KeyCode::Char('g'), client.clone()));
        assert!(view.graph_mode);
        assert!(view.graph_request.is_some());
        assert!(view.request.is_none());
        view.abort();
        let graph = graph_view().graph.clone().unwrap();
        let scope = GraphScope {
            binding: view.binding.clone().unwrap(),
            client,
            generation: view.generation,
        };
        view.graph_request = Some(tokio::spawn(async move { (scope, Ok(graph)) }));
        view.complete().await;
        assert!(view.graph.is_some());
        assert!(view.text(Instant::now()).contains("Flat execution DAG"));
    }

    // spec: TUIG-RUNTIME-R010.11
    #[tokio::test]
    async fn graph_denial_panic_and_stale_replies_never_restore_protected_data() {
        for invalidation in [
            "denied",
            "panic",
            "generation",
            "client",
            "owner",
            "context",
            "run",
            "close",
        ] {
            let mut view = graph_view();
            let graph = view.graph.clone().unwrap();
            let scope = GraphScope {
                binding: view.binding.clone().unwrap(),
                client: view.client.as_ref().unwrap().clone(),
                generation: view.generation,
            };
            match invalidation {
                "generation" => view.abort(),
                "client" => view.client_updated(&client()),
                "owner" | "context" | "run" => {
                    let old = view.binding.as_ref().unwrap();
                    let binding = TaskCorrelation::from_task(&json!({"kind":"task",
                        "id":if invalidation == "owner" { "other-root" } else { old.task_id() },
                        "contextId":if invalidation == "context" { "other-context" } else { old.context_id() },
                        "status":{"state":"working"},
                        "metadata":{"arbora":{"runId":if invalidation == "run" { "other-run" } else { old.run_id().unwrap() }}}})).unwrap();
                    view.task_updated(Some(&binding));
                }
                "close" => view.close(),
                _ => {}
            }
            // Inject a late completion even after abort to exercise scope validation.
            view.graph_request = Some(tokio::spawn(async move {
                assert!(invalidation != "panic", "fixture panic");
                (
                    scope,
                    if invalidation == "denied" {
                        Err(ReadRefusal::Denied)
                    } else {
                        Ok(graph)
                    },
                )
            }));
            view.complete().await;
            assert!(view.graph.is_none(), "{invalidation}");
            assert!(view.spatial.is_none(), "{invalidation}");
            assert!(!view.spatial_visible, "{invalidation}");
            assert!(view.selected_step.is_none(), "{invalidation}");
            assert!(!view.pending());
            assert!(!view.text(Instant::now()).contains("event-2"));
            if invalidation == "denied" {
                assert!(view.text(Instant::now()).contains("denied"));
            }
        }
    }

    // spec: TUIG-RUNTIME-R010.11
    #[test]
    fn graph_task_refusal_close_and_client_replacement_clear_selection() {
        for reason in ["task", "close", "client"] {
            let mut view = graph_view();
            view.selected_step = Some(3);
            match reason {
                "task" => view.task_updated(None),
                "close" => view.close(),
                _ => view.client_updated(&client()),
            }
            assert!(view.graph.is_none());
            assert!(view.spatial.is_none());
            assert!(!view.spatial_visible);
            assert!(view.selected_step.is_none());
            assert!(!view.text(Instant::now()).contains("event-2"));
        }
    }

    // spec: TUIG-RUNTIME-R010.11
    #[tokio::test]
    async fn canceled_complete_future_keeps_join_handle_and_rejects_stale_scope() {
        use std::sync::atomic::{AtomicBool, Ordering};

        for stale in [false, true] {
            let mut view = graph_view();
            let graph = view.graph.clone().unwrap();
            view.clear_read();
            let scope = GraphScope {
                binding: view.binding.clone().unwrap(),
                client: view.client.as_ref().unwrap().clone(),
                generation: view.generation,
            };
            let release = Arc::new(AtomicBool::new(false));
            let gate = release.clone();
            view.graph_request = Some(tokio::spawn(async move {
                while !gate.load(Ordering::Acquire) {
                    tokio::task::yield_now().await;
                }
                (scope, Ok(graph))
            }));
            let id = view.graph_request.as_ref().unwrap().id();
            // Biased order polls complete first; the closed gate forces Pending.
            tokio::select! {
                biased;
                _ = view.complete() => panic!("The read cannot complete before release"),
                _ = std::future::ready(()) => {}
            }
            assert_eq!(view.graph_request.as_ref().unwrap().id(), id);
            assert!(view.graph.is_none());
            assert!(view.spatial.is_none());
            assert!(!view.spatial_visible);
            if stale {
                view.generation += 1;
            }
            release.store(true, Ordering::Release);
            view.complete().await;
            assert!(!view.pending());
            assert_eq!(view.graph.is_some(), !stale);
            assert_eq!(view.selected_step, if stale { None } else { Some(0) });
        }
    }
}
