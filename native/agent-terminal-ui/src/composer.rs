use agent_terminal_ui_native::TaskSubmission;
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use ratatui::{
    Frame,
    style::Style,
    widgets::{Block, Paragraph, Wrap},
};

#[derive(Default)]
pub struct Composer {
    text: String,
    notice: String,
    pub open: bool,
}

impl Composer {
    pub fn paste(&mut self, value: &str) {
        let value = value.replace("\r\n", "\n").replace('\r', "\n");
        if self.text.len() + value.len() > 65_536
            || value
                .chars()
                .any(|c| c.is_control() && c != '\n' && c != '\t')
        {
            self.notice = "Input rejected: maximum 65536 bytes; text only.".to_owned();
            return;
        }
        self.text.push_str(&value);
        self.notice.clear();
    }

    pub fn key(&mut self, key: KeyEvent) -> Option<TaskSubmission> {
        match key.code {
            KeyCode::Esc => self.open = false,
            KeyCode::Char('j') if key.modifiers == KeyModifiers::CONTROL => self.paste("\n"),
            KeyCode::Enter if key.modifiers.is_empty() => match TaskSubmission::new(&self.text) {
                Ok(submission) => return Some(submission),
                Err(error) => self.notice = error.to_owned(),
            },
            KeyCode::Backspace => {
                self.text.pop();
                self.notice.clear();
            }
            KeyCode::Char(c)
                if !key
                    .modifiers
                    .intersects(KeyModifiers::CONTROL | KeyModifiers::ALT) =>
            {
                self.paste(&c.to_string())
            }
            _ => {}
        }
        None
    }

    pub fn draw(&self, frame: &mut Frame, style: Style, border: Style) {
        let block = Block::bordered()
            .title("Compose one task")
            .border_style(border)
            .title_style(border);
        let area = frame.area();
        let inner = block.inner(area);
        let text = format!(
            "Enter: submit | Ctrl+J: newline | Escape: review | Ctrl+C: quit\nOne new task only; no conversation continuation.\n{}\n\n{}▏",
            self.notice, self.text
        );
        let paragraph = Paragraph::new(text).style(style).wrap(Wrap { trim: false });
        let offset = paragraph
            .line_count(inner.width)
            .saturating_sub(usize::from(inner.height));
        frame.render_widget(
            paragraph
                .scroll((offset.min(u16::MAX as usize) as u16, 0))
                .block(block),
            area,
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn key(code: KeyCode) -> KeyEvent {
        KeyEvent::new(code, KeyModifiers::NONE)
    }

    // spec: TUI-RUNTIME-R012.1.3
    #[test]
    fn input_keys_stay_text_and_escape_preserves_draft() {
        let mut composer = Composer {
            open: true,
            ..Composer::default()
        };
        for c in "qclixp界".chars() {
            assert!(composer.key(key(KeyCode::Char(c))).is_none());
        }
        composer.key(key(KeyCode::Backspace));
        composer.key(key(KeyCode::Esc));
        assert!(!composer.open);
        assert_eq!(composer.text, "qclixp");
        assert!(composer.key(key(KeyCode::Enter)).is_some());
    }

    // spec: TUI-RUNTIME-R012.1.3
    #[test]
    fn paste_is_atomic_bounded_and_normalizes_newlines() {
        let mut composer = Composer::default();
        assert!(composer.key(key(KeyCode::Enter)).is_none());
        composer.paste("α\r\nβ\rγ");
        assert_eq!(composer.text, "α\nβ\nγ");
        composer.paste("\u{1b}[31m");
        composer.paste(&"a".repeat(65_536));
        assert_eq!(composer.text, "α\nβ\nγ");
        composer.key(KeyEvent::new(KeyCode::Char('j'), KeyModifiers::CONTROL));
        assert!(composer.text.ends_with('\n'));
    }
}
