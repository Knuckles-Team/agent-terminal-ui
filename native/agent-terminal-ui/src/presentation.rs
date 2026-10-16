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

    // spec: TUI-RUNTIME-R008.2
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
