//! Native presentation tokens from the existing Textual built-in themes.

use crossterm::event::{KeyCode, KeyEvent, KeyEventKind, KeyModifiers};
use ratatui::style::{Color, Style};

const THEMES: [&str; 4] = ["tokyo-night", "nord", "gruvbox", "textual-light"];

pub struct ThemeSelection {
    index: usize,
    no_color: bool,
}

impl ThemeSelection {
    pub fn new(theme: &str, no_color: &str) -> Self {
        Self {
            index: THEMES.iter().position(|name| *name == theme).unwrap_or(0),
            no_color: !no_color.is_empty(),
        }
    }

    pub fn style(&self) -> Style {
        presentation_style(THEMES[self.index], if self.no_color { "1" } else { "" })
    }

    pub fn key(&mut self, key: KeyEvent) -> bool {
        if key.code != KeyCode::F(6)
            || key.kind != KeyEventKind::Press
            || key.modifiers != KeyModifiers::NONE
        {
            return false;
        }
        self.index = (self.index + 1) % THEMES.len();
        true
    }
}

pub fn presentation_style(theme: &str, no_color: &str) -> Style {
    if !no_color.is_empty() {
        return Style::reset();
    }
    let (foreground, background) = match theme {
        "nord" => (0xd8dee9, 0x2e3440),
        "gruvbox" => (0xfbf1c7, 0x282828),
        "textual-light" => (0x1f1f1f, 0xe0e0e0),
        _ => (0xa9b1d6, 0x1a1b26),
    };
    Style::new()
        .fg(Color::from_u32(foreground))
        .bg(Color::from_u32(background))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::draw;
    use ratatui::{Terminal, backend::TestBackend};

    fn luminance(color: Color) -> f64 {
        let Color::Rgb(r, g, b) = color else {
            panic!("expected an RGB baseline token");
        };
        let linear = |channel: u8| {
            let value = f64::from(channel) / 255.0;
            if value <= 0.04045 {
                value / 12.92
            } else {
                ((value + 0.055) / 1.055).powf(2.4)
            }
        };
        0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)
    }

    // spec: TUI-RUNTIME-R008.2.1
    #[test]
    fn baseline_themes_render_readable_static_text() {
        for (theme, foreground, background) in [
            ("tokyo-night", 0xa9b1d6, 0x1a1b26),
            ("nord", 0xd8dee9, 0x2e3440),
            ("gruvbox", 0xfbf1c7, 0x282828),
            ("textual-light", 0x1f1f1f, 0xe0e0e0),
        ] {
            let style = presentation_style(theme, "");
            let fg = Color::from_u32(foreground);
            let bg = Color::from_u32(background);
            let (a, b) = (luminance(fg), luminance(bg));
            assert!((a.max(b) + 0.05) / (a.min(b) + 0.05) >= 4.5, "{theme}");
            let mut terminal = Terminal::new(TestBackend::new(40, 16)).unwrap();
            terminal
                .draw(|frame| draw(frame, "State: failed", style))
                .unwrap();
            let first = terminal.backend().buffer().clone();
            assert_eq!(first[(1, 1)].fg, fg);
            assert_eq!(first[(1, 1)].bg, bg);
            terminal
                .draw(|frame| draw(frame, "State: failed", style))
                .unwrap();
            assert_eq!(&first, terminal.backend().buffer());
            for no_color in ["1", "0", "false"] {
                terminal
                    .draw(|frame| draw(frame, "State: failed", presentation_style(theme, no_color)))
                    .unwrap();
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
}

/// Requested and visible rows are separate so transient refresh text cannot
/// discard the person's place in the longer result that follows.
#[derive(Default)]
pub struct Viewport {
    requested: u16,
    visible: u16,
    maximum: u16,
    height: u16,
}

impl Viewport {
    pub fn measure(&mut self, rows: usize, height: u16) {
        self.height = height;
        self.maximum = rows
            .saturating_sub(usize::from(height))
            .min(usize::from(u16::MAX)) as u16;
        self.visible = self.requested.min(self.maximum);
    }

    pub fn offset(&self) -> u16 {
        self.visible
    }

    pub fn handle(&mut self, key: crossterm::event::KeyCode) -> bool {
        use crossterm::event::KeyCode;
        let page = self.height.max(1);
        self.requested = match key {
            KeyCode::Up => self.visible.saturating_sub(1),
            KeyCode::Down => self.visible.saturating_add(1).min(self.maximum),
            KeyCode::PageUp => self.visible.saturating_sub(page),
            KeyCode::PageDown => self.visible.saturating_add(page).min(self.maximum),
            KeyCode::Home => 0,
            KeyCode::End => u16::MAX,
            _ => return false,
        };
        self.visible = self.requested.min(self.maximum);
        true
    }
}

#[cfg(test)]
mod viewport_tests {
    use super::*;
    use crate::draw_viewport;
    use crossterm::event::KeyCode;
    use ratatui::{Terminal, backend::TestBackend};

    fn contents(terminal: &Terminal<TestBackend>) -> String {
        terminal
            .backend()
            .buffer()
            .content()
            .iter()
            .map(|cell| cell.symbol())
            .collect()
    }

    #[test]
    fn arrows_scroll_one_wrapped_row_and_restore_it_after_refresh() {
        let status = "界界界界界界\ne\u{301}e\u{301}\nabcdefghijklmnop";
        let mut terminal = Terminal::new(TestBackend::new(12, 5)).unwrap();
        let mut viewport = Viewport::default();
        terminal
            .draw(|frame| draw_viewport(frame, status, Style::default(), &mut viewport, false))
            .unwrap();
        assert!(viewport.handle(KeyCode::Up));
        assert_eq!(viewport.offset(), 0);
        assert!(viewport.handle(KeyCode::Down));
        terminal
            .draw(|frame| draw_viewport(frame, status, Style::default(), &mut viewport, false))
            .unwrap();
        assert_eq!(viewport.offset(), 1);
        // The second wrapped row has one wide glyph, not the next logical line.
        assert_eq!(terminal.backend().buffer()[(1, 1)].symbol(), "界");
        assert_eq!(terminal.backend().buffer()[(3, 1)].symbol(), " ");
        assert_eq!(terminal.backend().buffer()[(1, 2)].symbol(), "e\u{301}");
        terminal
            .draw(|frame| {
                draw_viewport(frame, "Reading...", Style::default(), &mut viewport, false)
            })
            .unwrap();
        // The help footer still wraps beyond this tiny viewport during refresh.
        assert_eq!(viewport.offset(), 1);
        viewport.measure(1, 3);
        assert_eq!(viewport.offset(), 0);
        terminal
            .draw(|frame| draw_viewport(frame, status, Style::default(), &mut viewport, false))
            .unwrap();
        assert_eq!(viewport.offset(), 1);
        assert!(viewport.handle(KeyCode::Up));
        terminal
            .draw(|frame| draw_viewport(frame, status, Style::default(), &mut viewport, false))
            .unwrap();
        assert_eq!(viewport.offset(), 0);
        assert_eq!(terminal.backend().buffer()[(9, 1)].symbol(), "界");
    }

    #[test]
    fn arrows_clamp_at_both_ends_and_in_empty_viewports() {
        let mut viewport = Viewport::default();
        viewport.measure(5, 3);
        for _ in 0..4 {
            assert!(viewport.handle(KeyCode::Down));
        }
        assert_eq!(viewport.offset(), 2);
        assert!(viewport.handle(KeyCode::Up));
        assert_eq!(viewport.offset(), 1);
        for _ in 0..4 {
            assert!(viewport.handle(KeyCode::Up));
        }
        assert_eq!(viewport.offset(), 0);
        for height in [0, 1, 2] {
            viewport.measure(0, height);
            assert!(viewport.handle(KeyCode::Down));
            assert_eq!(viewport.offset(), 0);
            assert!(viewport.handle(KeyCode::Up));
            assert_eq!(viewport.offset(), 0);
        }
    }

    // spec: TUI-RUNTIME-R008.2.2
    #[test]
    fn paging_refresh_and_resize_preserve_requested_position() {
        let status = (0..40)
            .map(|index| format!("row-{index:03} 界e\u{301}"))
            .collect::<Vec<_>>()
            .join("\n");
        let mut terminal = Terminal::new(TestBackend::new(24, 8)).unwrap();
        let mut viewport = Viewport::default();
        terminal
            .draw(|frame| draw_viewport(frame, &status, Style::default(), &mut viewport, false))
            .unwrap();
        assert!(contents(&terminal).contains("row-000"));
        assert!(viewport.handle(KeyCode::PageDown));
        terminal
            .draw(|frame| draw_viewport(frame, &status, Style::default(), &mut viewport, false))
            .unwrap();
        assert_eq!(viewport.offset(), 6);
        assert!(contents(&terminal).contains("row-006"));
        assert!(!contents(&terminal).contains("row-000"));
        let before = terminal.backend().buffer().clone();
        terminal
            .draw(|frame| {
                draw_viewport(frame, "Reading...", Style::default(), &mut viewport, false)
            })
            .unwrap();
        for (width, height) in [(40, 12), (16, 6), (24, 8)] {
            terminal.backend_mut().resize(width, height);
            terminal.autoresize().unwrap();
            terminal
                .draw(|frame| draw_viewport(frame, &status, Style::default(), &mut viewport, false))
                .unwrap();
            assert_eq!(viewport.offset(), 6);
        }
        assert_eq!(&before, terminal.backend().buffer());
        viewport.handle(KeyCode::PageUp);
        assert_eq!(viewport.offset(), 0);
        viewport.handle(KeyCode::End);
        terminal
            .draw(|frame| draw_viewport(frame, &status, Style::default(), &mut viewport, false))
            .unwrap();
        assert!(contents(&terminal).contains("quit"));
        assert!(!contents(&terminal).contains("row-000"));
        viewport.handle(KeyCode::Home);
        terminal
            .draw(|frame| draw_viewport(frame, &status, Style::default(), &mut viewport, false))
            .unwrap();
        assert!(contents(&terminal).contains("row-000"));
        assert!(!viewport.handle(KeyCode::Char('x')));
    }

    // spec: TUI-RUNTIME-R008.2.2
    #[test]
    fn wrapping_keeps_wide_and_combining_graphemes_intact() {
        let mut terminal = Terminal::new(TestBackend::new(12, 8)).unwrap();
        let mut viewport = Viewport::default();
        terminal
            .draw(|frame| {
                draw_viewport(
                    frame,
                    "界界界界界界\ne\u{301}e\u{301}\nabcdefghijklmnop",
                    Style::default(),
                    &mut viewport,
                    false,
                )
            })
            .unwrap();
        let buffer = terminal.backend().buffer();
        assert_eq!(buffer[(1, 1)].symbol(), "界");
        assert_eq!(buffer[(9, 1)].symbol(), "界");
        assert_eq!(buffer[(1, 2)].symbol(), "界");
        assert_eq!(buffer[(1, 3)].symbol(), "e\u{301}");
        assert_eq!(buffer[(2, 3)].symbol(), "e\u{301}");
        assert!(contents(&terminal).contains("abcdefghij"));
        assert!(contents(&terminal).contains("klmnop"));
    }

    // spec: TUI-RUNTIME-R008.2.2
    #[test]
    fn tiny_viewports_and_shorter_results_clamp_without_losing_place() {
        let mut viewport = Viewport::default();
        viewport.measure(100, 8);
        viewport.handle(KeyCode::End);
        assert_eq!(viewport.offset(), 92);
        viewport.measure(2, 8);
        assert_eq!(viewport.offset(), 0);
        viewport.measure(100, 8);
        assert_eq!(viewport.offset(), 92);
        for size in [0, 1, 2, 3] {
            let mut terminal = Terminal::new(TestBackend::new(size, size)).unwrap();
            terminal
                .draw(|frame| {
                    draw_viewport(frame, "界e\u{301}", Style::default(), &mut viewport, false)
                })
                .unwrap();
            viewport.handle(KeyCode::PageDown);
            viewport.handle(KeyCode::PageUp);
        }
    }
}

#[cfg(test)]
mod theme_switch_tests {
    use super::*;
    use crate::{
        draw_confirmation, draw_viewport, host_log_view::HostLogView, inspector_view::InspectorView,
    };
    use ratatui::{Terminal, backend::TestBackend};
    use std::time::Instant;

    fn switch(themes: &mut ThemeSelection) {
        assert!(themes.key(KeyEvent::new(KeyCode::F(6), KeyModifiers::NONE)));
    }

    // spec: TUI-RUNTIME-R008.2.3.2.1
    #[test]
    fn runtime_switch_renders_each_palette_in_all_views() {
        let mut themes = ThemeSelection::new("unknown", "");
        let mut terminal = Terminal::new(TestBackend::new(80, 24)).unwrap();
        let mut inspector = InspectorView::default();
        let mut logs = HostLogView::default();
        let mut viewport = Viewport::default();
        for theme in THEMES.into_iter().chain([THEMES[0]]) {
            let expected = presentation_style(theme, "");
            assert_eq!(themes.style(), expected);
            for view in 0..4 {
                terminal
                    .draw(|frame| match view {
                        0 => draw_viewport(
                            frame,
                            "Task: working",
                            themes.style(),
                            &mut viewport,
                            false,
                        ),
                        1 => inspector.draw(frame, themes.style(), Instant::now()),
                        2 => logs.draw(frame, themes.style()),
                        _ => {
                            draw_confirmation(frame, "Task: working", themes.style());
                        }
                    })
                    .unwrap();
                let cell = &terminal.backend().buffer()[(1, 1)];
                assert_eq!(cell.fg, expected.fg.unwrap());
                assert_eq!(cell.bg, expected.bg.unwrap());
            }
            switch(&mut themes);
        }
    }

    // spec: TUI-RUNTIME-R008.2.3.2.1
    #[test]
    fn runtime_switch_preserves_scroll_and_no_color() {
        let status = (0..100).map(|n| format!("row {n}\n")).collect::<String>();
        let mut terminal = Terminal::new(TestBackend::new(40, 10)).unwrap();
        for no_color in ["", "1", "0", "false"] {
            let mut themes = ThemeSelection::new("gruvbox", no_color);
            let mut viewport = Viewport::default();
            terminal
                .draw(|frame| draw_viewport(frame, &status, themes.style(), &mut viewport, false))
                .unwrap();
            viewport.handle(KeyCode::PageDown);
            let offset = viewport.offset();
            for _ in 0..5 {
                switch(&mut themes);
                terminal
                    .draw(|frame| {
                        draw_viewport(frame, &status, themes.style(), &mut viewport, false)
                    })
                    .unwrap();
                assert_eq!(viewport.offset(), offset);
                let cell = &terminal.backend().buffer()[(1, 1)];
                assert_eq!(cell.symbol(), "r");
                if !no_color.is_empty() {
                    assert_eq!((cell.fg, cell.bg), (Color::Reset, Color::Reset));
                }
            }
        }
    }

    // spec: TUI-RUNTIME-R008.2.3.2.1
    #[test]
    fn only_unmodified_f6_presses_switch_the_theme() {
        let mut themes = ThemeSelection::new("nord", "");
        for key in [
            KeyEvent::new_with_kind(KeyCode::F(6), KeyModifiers::NONE, KeyEventKind::Repeat),
            KeyEvent::new_with_kind(KeyCode::F(6), KeyModifiers::NONE, KeyEventKind::Release),
            KeyEvent::new(KeyCode::F(6), KeyModifiers::CONTROL),
            KeyEvent::new(KeyCode::F(6), KeyModifiers::ALT),
            KeyEvent::new(KeyCode::F(6), KeyModifiers::SHIFT),
            KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE),
            KeyEvent::new(KeyCode::Char('y'), KeyModifiers::NONE),
        ] {
            assert!(!themes.key(key));
            assert_eq!(themes.style(), presentation_style("nord", ""));
        }
        switch(&mut themes);
        assert_eq!(themes.style(), presentation_style("gruvbox", ""));
    }
}
