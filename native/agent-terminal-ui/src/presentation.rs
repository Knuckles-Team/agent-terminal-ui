//! Native presentation tokens from the existing Textual built-in themes.

use ratatui::style::{Color, Style};

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
