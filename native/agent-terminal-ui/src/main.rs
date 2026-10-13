use agent_terminal_ui_native::GraphOsClient;
use crossterm::event::{Event, EventStream, KeyCode, KeyEventKind, KeyModifiers};
use futures_util::StreamExt;
use ratatui::{
    Frame,
    style::{Color, Style},
    widgets::{Block, Paragraph, Wrap},
};
use std::{env, process::ExitCode, sync::Arc};

fn presentation_style(theme: &str, no_color: &str) -> Style {
    if !no_color.is_empty() {
        return Style::reset();
    }
    match theme {
        "tokyo-night" => Style::new()
            .fg(Color::Rgb(169, 177, 214))
            .bg(Color::Rgb(26, 27, 38)),
        _ => presentation_style("tokyo-night", no_color),
    }
}

fn draw(frame: &mut Frame, status: &str, style: Style) {
    let text = format!(
        "{status}\n\nDiscovery only. Task streaming and approvals remain unavailable.\n\nr: retry discovery | c: cancel local request | q / Ctrl+C: quit"
    );
    frame.render_widget(
        Paragraph::new(text)
            .style(style)
            .wrap(Wrap { trim: false })
            .block(Block::bordered().title("GraphOS")),
        frame.area(),
    );
}

async fn run(client: Arc<GraphOsClient>) -> Result<(), &'static str> {
    let theme = env::var("AGENT_THEME").unwrap_or_else(|_| "tokyo-night".to_owned());
    let no_color = env::var("NO_COLOR").unwrap_or_default();
    let style = presentation_style(&theme, &no_color);
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
            terminal.draw(|frame| draw(frame, &status, style)).map_err(|_| "Cannot draw terminal")?;
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
    use super::{draw, presentation_style};
    use ratatui::style::{Color, Style};
    use ratatui::{Terminal, backend::TestBackend};

    // spec: TUI-RUNTIME-R002.7
    #[test]
    fn renders_refusal_without_enabling_task_actions() {
        let mut terminal = Terminal::new(TestBackend::new(100, 10)).unwrap();
        terminal
            .draw(|frame| {
                draw(
                    frame,
                    "GraphOS discovery refused or unavailable",
                    Style::default(),
                )
            })
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

    // spec: TUI-RUNTIME-R008.1
    #[test]
    fn resize_preserves_wrapped_status_and_keyboard_help() {
        let mut terminal = Terminal::new(TestBackend::new(100, 16)).unwrap();
        let status = "Local discovery canceled. No remote task was canceled.";
        for width in [100, 40, 100] {
            terminal.backend_mut().resize(width, 16);
            terminal.autoresize().unwrap();
            terminal
                .draw(|frame| draw(frame, status, Style::default()))
                .unwrap();
            let buffer = terminal.backend().buffer();
            let lines: Vec<String> = (1..15)
                .map(|y| (1..width - 1).map(|x| buffer[(x, y)].symbol()).collect())
                .collect();
            let text = lines
                .iter()
                .map(|line| line.trim())
                .collect::<Vec<_>>()
                .join(" ");
            assert!(
                text.contains(status),
                "status clipped at {width} columns: {text}"
            );
            for help in [
                "r: retry discovery",
                "c: cancel local request",
                "q / Ctrl+C: quit",
            ] {
                assert!(
                    text.contains(help),
                    "help clipped at {width} columns: {text}"
                );
            }
        }
    }

    // spec: TUI-RUNTIME-R008.1
    #[test]
    fn renderer_honors_no_color_and_unknown_theme_fallback() {
        let default_style = presentation_style("tokyo-night", "");
        assert_eq!(presentation_style("unknown-theme", ""), default_style);
        let mut terminal = Terminal::new(TestBackend::new(40, 16)).unwrap();
        for (theme, no_color) in [
            ("tokyo-night", ""),
            ("unknown-theme", ""),
            ("tokyo-night", "1"),
            ("unknown-theme", "0"),
        ] {
            terminal
                .draw(|frame| {
                    draw(
                        frame,
                        "Discovering GraphOS...",
                        presentation_style(theme, no_color),
                    )
                })
                .unwrap();
            let cell = &terminal.backend().buffer()[(1, 1)];
            if no_color.is_empty() {
                assert_eq!(cell.fg, Color::Rgb(169, 177, 214));
                assert_eq!(cell.bg, Color::Rgb(26, 27, 38));
            } else {
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
