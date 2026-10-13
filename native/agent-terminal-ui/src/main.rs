use agent_terminal_ui_native::GraphOsClient;
use crossterm::event::{Event, EventStream, KeyCode, KeyEventKind, KeyModifiers};
use futures_util::StreamExt;
use ratatui::{
    Frame,
    widgets::{Block, Paragraph},
};
use std::{env, process::ExitCode, sync::Arc};

fn draw(frame: &mut Frame, status: &str) {
    let text = format!(
        "{status}\n\nDiscovery only. Task streaming and approvals remain unavailable.\n\nr: retry discovery | c: cancel local request | q / Ctrl+C: quit"
    );
    frame.render_widget(
        Paragraph::new(text).block(Block::bordered().title("GraphOS")),
        frame.area(),
    );
}

async fn run(client: Arc<GraphOsClient>) -> Result<(), &'static str> {
    let mut terminal = ratatui::init();
    let mut events = EventStream::new();
    let mut request = tokio::spawn({
        let client = client.clone();
        async move { client.discover().await }
    });
    let mut pending = true;
    let mut status = String::from("Discovering GraphOS...");
    let result = async {
        loop {
            terminal.draw(|frame| draw(frame, &status)).map_err(|_| "Cannot draw terminal")?;
            tokio::select! {
                result = &mut request, if pending => {
                    pending = false;
                    status = match result {
                        Ok(Ok(name)) => format!("Agent Card received: {name}"),
                        Ok(Err(error)) => error.to_owned(),
                        Err(_) => "Discovery request interrupted".to_owned(),
                    };
                }
                event = events.next() => {
                    let Some(Ok(event)) = event else { return Err("Terminal input unavailable"); };
                    if let Event::Key(key) = event {
                        if key.kind != KeyEventKind::Press { continue; }
                        if key.code == KeyCode::Char('q') || (key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL)) {
                            return Ok(());
                        }
                        match key.code {
                            KeyCode::Char('c') if pending => {
                                request.abort();
                                pending = false;
                                status = "Local discovery canceled. No remote task was canceled.".to_owned();
                            }
                            KeyCode::Char('r') if !pending => {
                                let client = client.clone();
                                request = tokio::spawn(async move { client.discover().await });
                                pending = true;
                                status = "Discovering GraphOS...".to_owned();
                            }
                            _ => {}
                        }
                    }
                }
            }
        }
    }.await;
    request.abort();
    ratatui::restore();
    result
}

#[tokio::main]
async fn main() -> ExitCode {
    let endpoint = env::var("AGENT_URL").unwrap_or_else(|_| "http://localhost:8000".to_owned());
    let token = env::var("AGENT_BEARER_TOKEN").ok();
    let result = match GraphOsClient::new(&endpoint, token.as_deref()) {
        Ok(client) => run(Arc::new(client)).await,
        Err(error) => Err(error),
    };
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
    use super::draw;
    use ratatui::{Terminal, backend::TestBackend};

    // spec: TUI-RUNTIME-R002.7
    #[test]
    fn renders_refusal_without_enabling_task_actions() {
        let mut terminal = Terminal::new(TestBackend::new(100, 10)).unwrap();
        terminal
            .draw(|frame| draw(frame, "GraphOS discovery refused or unavailable"))
            .unwrap();
        let text: String = terminal
            .backend()
            .buffer()
            .content()
            .iter()
            .map(|cell| cell.symbol())
            .collect();
        assert!(text.contains("GraphOS discovery refused"));
        assert!(text.contains("Task streaming and approvals remain unavailable"));
    }
}
