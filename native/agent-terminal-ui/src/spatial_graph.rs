//! A terminal-only layout of the already validated flat execution graph.

use crate::presentation::Viewport;
use agent_terminal_ui_native::{execution_graph::ExecutionGraph, public_run_events::literal};
use crossterm::event::KeyCode;
use ratatui::{
    Frame,
    buffer::Buffer,
    layout::Rect,
    style::{Modifier, Style},
    text::Line,
    widgets::{Block, BorderType, Paragraph, Widget},
};

const NODE_WIDTH: u16 = 22;
const NODE_HEIGHT: u16 = 4;
const COLUMN: u16 = NODE_WIDTH + 6;
const ROW: u16 = NODE_HEIGHT + 2;

#[derive(Debug, PartialEq, Eq)]
struct LayeredLayout {
    positions: Vec<(u16, u16)>,
    width: u16,
    height: u16,
}

impl LayeredLayout {
    fn new(graph: &ExecutionGraph) -> Self {
        let count = graph.nodes.len();
        let mut layers = vec![0_u16; count];
        let mut incoming = vec![0; count];
        for &(_, target) in &graph.edges {
            incoming[target] += 1;
        }
        let mut ready: Vec<_> = (0..count).filter(|&i| incoming[i] == 0).collect();
        while let Some(source) = ready.pop() {
            for &(_, target) in graph.edges.iter().filter(|(from, _)| *from == source) {
                layers[target] = layers[target].max(layers[source] + 1);
                incoming[target] -= 1;
                if incoming[target] == 0 {
                    ready.push(target);
                }
            }
        }
        let mut rows = vec![0; count];
        let positions: Vec<_> = layers
            .into_iter()
            .map(|layer| {
                let row = &mut rows[usize::from(layer)];
                let position = (layer * COLUMN, *row * ROW);
                *row += 1;
                position
            })
            .collect();
        Self {
            width: positions
                .iter()
                .map(|(x, _)| x + NODE_WIDTH)
                .max()
                .unwrap_or(0),
            height: positions
                .iter()
                .map(|(_, y)| y + NODE_HEIGHT + 1)
                .max()
                .unwrap_or(0),
            positions,
        }
    }
}

pub struct SpatialGraph {
    layout: LayeredLayout,
    horizontal: Viewport,
    vertical: Viewport,
    focus: bool,
    size: (u16, u16),
}

impl SpatialGraph {
    pub fn new(graph: &ExecutionGraph) -> Self {
        Self {
            layout: LayeredLayout::new(graph),
            horizontal: Viewport::default(),
            vertical: Viewport::default(),
            focus: true,
            size: (0, 0),
        }
    }

    pub fn focus_selected(&mut self) {
        self.focus = true;
    }

    pub fn key(&mut self, key: KeyCode) {
        match key {
            KeyCode::Left => {
                self.horizontal.handle(KeyCode::Up);
            }
            KeyCode::Right => {
                self.horizontal.handle(KeyCode::Down);
            }
            KeyCode::Home => self.focus_selected(),
            _ => {
                self.vertical.handle(key);
            }
        }
    }

    pub fn draw(
        &mut self,
        frame: &mut Frame,
        area: Rect,
        graph: &ExecutionGraph,
        selected: usize,
        style: Style,
    ) {
        self.horizontal
            .measure(usize::from(self.layout.width), area.width);
        self.vertical
            .measure(usize::from(self.layout.height), area.height);
        let resized = self.size != (area.width, area.height);
        self.size = (area.width, area.height);
        if (std::mem::take(&mut self.focus) || resized)
            && let Some(&(x, y)) = self.layout.positions.get(selected)
        {
            self.horizontal
                .reveal(usize::from(x), usize::from(NODE_WIDTH));
            self.vertical
                .reveal(usize::from(y), usize::from(NODE_HEIGHT));
        }
        frame.render_widget(
            GraphWidget {
                graph,
                layout: &self.layout,
                selected,
                x: self.horizontal.offset(),
                y: self.vertical.offset(),
                style,
            },
            area,
        );
    }
}

pub fn label(value: &str) -> String {
    literal(value).replace(['\n', '\t'], " ")
}

struct GraphWidget<'a> {
    graph: &'a ExecutionGraph,
    layout: &'a LayeredLayout,
    selected: usize,
    x: u16,
    y: u16,
    style: Style,
}

impl GraphWidget<'_> {
    fn cell(&self, buffer: &mut Buffer, area: Rect, x: u16, y: u16, symbol: char) {
        if x >= self.x && y >= self.y && x - self.x < area.width && y - self.y < area.height {
            buffer[(area.x + x - self.x, area.y + y - self.y)]
                .set_char(symbol)
                .set_style(self.style);
        }
    }

    fn horizontal(&self, buffer: &mut Buffer, area: Rect, left: u16, right: u16, y: u16) {
        for x in left.max(self.x)..=right.min(self.x.saturating_add(area.width)) {
            self.cell(buffer, area, x, y, '-');
        }
    }

    fn vertical(&self, buffer: &mut Buffer, area: Rect, x: u16, top: u16, bottom: u16) {
        for y in top.max(self.y)..=bottom.min(self.y.saturating_add(area.height)) {
            self.cell(buffer, area, x, y, '|');
        }
    }
}

impl Widget for GraphWidget<'_> {
    fn render(self, area: Rect, buffer: &mut Buffer) {
        buffer.set_style(area, self.style);
        for &(from, to) in &self.graph.edges {
            let (x1, y1) = self.layout.positions[from];
            let (x2, y2) = self.layout.positions[to];
            let (start, end, middle) = (x1 + NODE_WIDTH, x2 - 2, x1 + NODE_WIDTH + 2);
            // Route long dependencies through gutters, never through another card.
            let lane = y2 + NODE_HEIGHT;
            self.horizontal(buffer, area, start, middle, y1 + 1);
            self.vertical(buffer, area, middle, (y1 + 1).min(lane), (y1 + 1).max(lane));
            self.horizontal(buffer, area, middle, end, lane);
            self.vertical(buffer, area, end, y2 + 1, lane);
            self.cell(buffer, area, end + 1, y2 + 1, '>');
        }
        for (index, (&(x, y), node)) in self
            .layout
            .positions
            .iter()
            .zip(&self.graph.nodes)
            .enumerate()
        {
            let node_area = Rect::new(x, y, NODE_WIDTH, NODE_HEIGHT);
            let visible =
                node_area.intersection(Rect::new(self.x, self.y, area.width, area.height));
            if visible.is_empty() {
                continue;
            }
            let selected = index == self.selected;
            let node_style = if selected {
                self.style.add_modifier(Modifier::REVERSED)
            } else {
                self.style
            };
            let mut card = Buffer::empty(Rect::new(0, 0, NODE_WIDTH, NODE_HEIGHT));
            Paragraph::new(vec![
                Line::from(label(&node.task_id)),
                Line::from(node.status.as_str()),
            ])
            .style(node_style)
            .block(
                Block::bordered()
                    .border_type(BorderType::Rounded)
                    .title(format!("{}{}", if selected { "> " } else { "" }, index + 1)),
            )
            .render(card.area, &mut card);
            for row in visible.y..visible.bottom() {
                for column in visible.x..visible.right() {
                    let source = &card[(column - x, row - y)];
                    let target = &mut buffer[(area.x + column - self.x, area.y + row - self.y)];
                    // Do not emit half of a wide glyph at the clipped right edge.
                    if Line::from(source.symbol()).width() > usize::from(visible.right() - column) {
                        target.set_char(' ').set_style(node_style);
                    } else {
                        *target = source.clone();
                    }
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use agent_terminal_ui_native::execution_graph::{ExecutionStep, MAX_NODES};
    use ratatui::{Terminal, backend::TestBackend};

    fn graph(count: usize, edges: Vec<(usize, usize)>) -> ExecutionGraph {
        ExecutionGraph {
            run_id: "run".to_owned(),
            task_id: "root".to_owned(),
            plan_digest: "plan".to_owned(),
            nodes: (0..count)
                .map(|i| ExecutionStep {
                    key: format!("key-{i}"),
                    task_id: format!("step-{i}"),
                    status: "unobserved".to_owned(),
                    evidence: None,
                })
                .collect(),
            edges,
            covered_after: 0,
            has_more: false,
        }
    }

    // spec: TUI-RUNTIME-R010.12.1, TUI-RUNTIME-R010.12.1.1
    #[test]
    fn layers_are_stable_for_diamond_chain_disconnected_and_maximum_graphs() {
        let mut diamond = graph(5, vec![(0, 1), (0, 2), (1, 3), (2, 3)]);
        let layout = LayeredLayout::new(&diamond);
        assert_eq!(
            layout.positions,
            vec![
                (0, 0),
                (COLUMN, 0),
                (COLUMN, ROW),
                (2 * COLUMN, 0),
                (0, ROW)
            ]
        );
        diamond.edges.reverse();
        assert_eq!(layout, LayeredLayout::new(&diamond));
        for edges in [
            Vec::new(),
            (1..MAX_NODES).map(|i| (i - 1, i)).collect(),
            (0..MAX_NODES)
                .flat_map(|from| ((from + 1)..MAX_NODES).map(move |to| (from, to)))
                .collect(),
        ] {
            let graph = graph(MAX_NODES, edges);
            let layout = LayeredLayout::new(&graph);
            assert_eq!(layout.positions.len(), MAX_NODES);
            assert!(usize::from(layout.width) <= MAX_NODES * usize::from(COLUMN));
            assert!(usize::from(layout.height) <= MAX_NODES * usize::from(ROW));
            for &(from, to) in &graph.edges {
                assert!(layout.positions[from].0 < layout.positions[to].0);
            }
        }
    }

    // spec: TUI-RUNTIME-R010.12.1, TUI-RUNTIME-R010.12.1.1, TUI-RUNTIME-R008.3
    #[test]
    fn bounded_pan_focus_resize_and_literal_labels_keep_graph_unchanged() {
        let mut graph = graph(MAX_NODES, (1..MAX_NODES).map(|i| (i - 1, i)).collect());
        graph.nodes[0].task_id = "\u{1b}[31m[bold]界\nforged\t\u{202e}".to_owned();
        let original = graph.clone();
        let mut map = SpatialGraph::new(&graph);
        let mut terminal = Terminal::new(TestBackend::new(80, 12)).unwrap();
        terminal
            .draw(|f| map.draw(f, f.area(), &graph, 0, Style::reset()))
            .unwrap();
        let first = terminal.backend().buffer().clone();
        let text: String = first.content().iter().map(|cell| cell.symbol()).collect();
        assert!(text.contains("[31m[bold]界"));
        assert!(text.contains("forged"));
        assert!(!text.contains('\u{1b}'));
        assert!(!text.contains('\u{202e}'));
        for _ in 0..10_000 {
            map.key(KeyCode::Right);
            map.key(KeyCode::Down);
        }
        terminal
            .draw(|f| map.draw(f, f.area(), &graph, 0, Style::reset()))
            .unwrap();
        assert_eq!(map.horizontal.offset(), map.layout.width - 80);
        assert_eq!(map.vertical.offset(), 0);
        map.key(KeyCode::Home);
        terminal
            .draw(|f| map.draw(f, f.area(), &graph, 0, Style::reset()))
            .unwrap();
        assert_eq!(&first, terminal.backend().buffer());
        map.focus_selected();
        terminal
            .draw(|f| map.draw(f, f.area(), &graph, MAX_NODES - 1, Style::reset()))
            .unwrap();
        assert_eq!(map.horizontal.offset(), map.layout.width - 80);
        for (width, height) in [(0, 0), (1, 1), (40, 8), (120, 24)] {
            terminal.backend_mut().resize(width, height);
            terminal.resize(Rect::new(0, 0, width, height)).unwrap();
            terminal
                .draw(|f| map.draw(f, f.area(), &graph, 0, Style::reset()))
                .unwrap();
            assert!(
                terminal
                    .backend()
                    .buffer()
                    .content()
                    .iter()
                    .all(|cell| cell.fg == ratatui::style::Color::Reset
                        && cell.bg == ratatui::style::Color::Reset)
            );
        }
        assert_eq!(graph, original);
    }
}
