use crate::presentation::Viewport;
use agent_terminal_ui_native::{
    GraphOsClient,
    host_logs::{HostLogs, LogBatch, REFUSED},
};
use crossterm::event::KeyCode;
use ratatui::{
    Frame,
    style::Style,
    widgets::{Block, Paragraph, Wrap},
};
use std::{collections::VecDeque, sync::Arc};
use tokio::task::JoinHandle;

type Read = JoinHandle<Result<(HostLogs, LogBatch), &'static str>>;

#[derive(Default)]
pub struct HostLogView {
    open: bool,
    request: Option<Read>,
    reader: Option<HostLogs>,
    lines: VecDeque<String>,
    status: &'static str,
    expires: u64,
    viewport: Viewport,
}

impl HostLogView {
    pub fn is_open(&self) -> bool {
        self.open
    }
    pub fn pending(&self) -> bool {
        self.request.is_some()
    }
    pub fn open(&mut self, client: Arc<GraphOsClient>) {
        self.close();
        self.open = true;
        self.status = "Reading authenticated host logs...";
        self.request = Some(tokio::spawn(async move {
            let mut reader = HostLogs::bind(client).await?;
            let batch = reader.read().await?;
            Ok((reader, batch))
        }));
    }
    pub fn close(&mut self) {
        if let Some(request) = self.request.take() {
            request.abort();
        }
        self.reader = None;
        self.lines.clear();
        self.expires = 0;
        self.open = false;
        self.viewport = Viewport::default();
    }
    pub fn tick(&mut self) {
        if !self.open {
            return;
        }
        if self.expires != 0 && !HostLogs::unexpired(self.expires) {
            self.refuse();
            return;
        }
        if self.pending() {
            return;
        }
        if let Some(mut reader) = self.reader.take() {
            self.request = Some(tokio::spawn(async move {
                let batch = reader.read().await?;
                Ok((reader, batch))
            }));
        }
    }
    fn refuse(&mut self) {
        self.close();
        self.open = true;
        self.status = REFUSED;
    }
    pub async fn complete(&mut self) {
        let Some(request) = self.request.as_mut() else {
            return;
        };
        let result = request.await;
        self.request = None;
        match result {
            Ok(Ok((reader, batch))) if reader.valid() => {
                self.expires = reader.expires_at_ms();
                self.reader = Some(reader);
                self.status = "Host logs | Escape: close";
                if batch.gap {
                    self.lines.push_back("[Log history gap]".to_owned());
                }
                for message in batch.messages {
                    for line in message.lines() {
                        self.lines.push_back(line.to_owned());
                        while self.lines.len() > 1000 {
                            self.lines.pop_front();
                        }
                    }
                }
                while self.lines.len() > 1000 {
                    self.lines.pop_front();
                }
            }
            _ => self.refuse(),
        }
    }
    pub fn key(&mut self, key: KeyCode) -> bool {
        if !self.open {
            return false;
        }
        match key {
            KeyCode::Esc | KeyCode::Char('l') => self.close(),
            _ => {
                self.viewport.handle(key);
            }
        }
        true
    }
    pub fn draw(&mut self, frame: &mut Frame, style: Style) {
        if self.expires != 0 && !HostLogs::unexpired(self.expires) {
            self.refuse();
        }
        let text = format!(
            "{}\n{}",
            self.status,
            self.lines.iter().cloned().collect::<Vec<_>>().join("\n")
        );
        let block = Block::bordered().title("Host logs");
        let inner = block.inner(frame.area());
        let paragraph = Paragraph::new(text).style(style).wrap(Wrap { trim: false });
        self.viewport
            .measure(paragraph.line_count(inner.width), inner.height);
        frame.render_widget(
            paragraph.scroll((self.viewport.offset(), 0)).block(block),
            frame.area(),
        );
    }
}

impl Drop for HostLogView {
    fn drop(&mut self) {
        self.close();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // spec: TUI-RUNTIME-R002.11
    #[tokio::test]
    async fn close_aborts_pending_read_and_clears_protected_lines() {
        let mut view = HostLogView {
            open: true,
            ..Default::default()
        };
        view.lines.push_back("protected".to_owned());
        let task = tokio::spawn(async { std::future::pending().await });
        let abort = task.abort_handle();
        view.request = Some(task);
        assert!(view.key(KeyCode::Esc));
        tokio::task::yield_now().await;
        assert!(abort.is_finished());
        assert!(!view.is_open());
        assert!(view.lines.is_empty());
        assert!(!view.pending());
    }

    // spec: TUI-RUNTIME-R002.11
    #[tokio::test]
    async fn denial_and_idle_expiry_clear_display_without_task_actions() {
        let mut view = HostLogView {
            open: true,
            ..Default::default()
        };
        view.lines.push_back("protected".to_owned());
        view.request = Some(tokio::spawn(async { Err(REFUSED) }));
        view.complete().await;
        assert!(view.lines.is_empty());
        assert_eq!(view.status, REFUSED);
        assert!(view.key(KeyCode::Char('x')));
        view.lines.push_back("protected".to_owned());
        view.expires = 1;
        view.tick();
        assert!(view.lines.is_empty());
        assert!(!view.pending());
    }
}
