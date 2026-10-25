use crate::{
    composer::Composer,
    local_runtime::{Options, finish_backend, spawn_backend},
    presentation::{ThemeSelection, Viewport, accepts_key_event},
};
use agent_terminal_ui_native::task_output::terminal_text;
use crossterm::event::{
    DisableBracketedPaste, DisableMouseCapture, Event, EventStream, KeyCode, KeyModifiers,
};
use futures_util::StreamExt;
use ratatui::{
    style::Style,
    widgets::{Block, Paragraph, Wrap},
};
use std::time::Duration;
use tokio::{
    sync::{mpsc, watch},
    time::timeout,
};

const TRANSCRIPT_BYTES: usize = 128 * 1024;
const TURN_LIMIT: usize = 64;

enum Update {
    Ready(&'static str),
    Text(String),
}

#[derive(Default)]
struct Transcript {
    text: String,
    clipped: bool,
}

impl Transcript {
    fn append(&mut self, text: &str) {
        self.text.push_str(&terminal_text(text));
        if self.text.len() > TRANSCRIPT_BYTES {
            let mut cut = self.text.len() - TRANSCRIPT_BYTES;
            while !self.text.is_char_boundary(cut) {
                cut += 1;
            }
            self.text.drain(..cut);
            self.clipped = true;
        }
    }
}

async fn signaled(signal: &mut watch::Receiver<bool>) {
    let _ = signal.wait_for(|value| *value).await;
}

async fn deliver(
    updates: &mpsc::Sender<Update>,
    quit: &mut watch::Receiver<bool>,
    update: Update,
) -> Result<(), &'static str> {
    tokio::select! {
        biased;
        _ = signaled(quit) => Err("Local session closed"),
        result = updates.send(update) => result.map_err(|_| "Local display closed"),
    }
}

async fn turn<R: tokio::io::AsyncRead + Unpin, W: tokio::io::AsyncWrite + Unpin>(
    client: &mut agent_terminal_ui_native::acp::TextClient<R, W>,
    text: &str,
    updates: &mpsc::Sender<Update>,
    cancel: &mut watch::Receiver<bool>,
    quit: &mut watch::Receiver<bool>,
) -> Result<&'static str, &'static str> {
    let id = tokio::select! {
        biased;
        _ = signaled(quit) => return Err("Local submission interrupted; outcome unknown. No replay."),
        _ = signaled(cancel) => return Err("Local submission interrupted; outcome unknown. No replay."),
        result = timeout(Duration::from_secs(5), client.prompt(text)) => result.map_err(|_| "Local submission timed out; outcome unknown. No replay.")??,
    };
    let result = tokio::select! {
        biased;
        _ = signaled(quit) => None,
        _ = signaled(cancel) => None,
        result = timeout(Duration::from_secs(330), client.response(id, |chunk: &str| {
            let update = Update::Text(terminal_text(chunk));
            let updates = updates.clone();
            async move { updates.send(update).await.map_err(|_| "Local display closed") }
        })) => Some(result),
    };
    let value = match result {
        Some(Ok(value)) => value?,
        Some(Err(_)) => {
            let _ = timeout(Duration::from_secs(5), async {
                client.cancel().await?;
                client.response(id, async |_| Ok(())).await
            })
            .await;
            return Err("Local turn timed out; session closed without replay.");
        }
        None => timeout(Duration::from_secs(5), async {
            client.cancel().await?;
            client.response(id, async |_| Ok(())).await
        })
        .await
        .map_err(|_| "Cancellation outcome unknown; session closed without replay.")??,
    };
    match value["stopReason"].as_str() {
        Some("end_turn") => Ok("Turn completed. p: compose next turn"),
        Some("cancelled") => Ok("Turn canceled (acknowledged). p: compose next turn"),
        _ => Err("Local turn outcome unavailable; session closed without replay."),
    }
}

async fn session(
    options: Options,
    mut commands: mpsc::Receiver<String>,
    updates: mpsc::Sender<Update>,
    mut cancel: watch::Receiver<bool>,
    mut quit: watch::Receiver<bool>,
) -> Result<(), &'static str> {
    let (mut child, client, cwd) = spawn_backend(&options.model)?;
    let mut client = client.with_sequential_turns();
    let result = async {
        tokio::select! {
            biased;
            _ = signaled(&mut quit) => return Ok(()),
            result = timeout(Duration::from_secs(30), client.initialize(&cwd)) => result.map_err(|_| "Local session initialization timed out")??,
        }
        deliver(&updates, &mut quit, Update::Ready("Local session ready. p: compose a turn")).await?;
        for _ in 0..TURN_LIMIT {
            let text = tokio::select! {
                biased;
                _ = signaled(&mut quit) => return Ok(()),
                result = client.idle() => return result,
                command = commands.recv() => match command { Some(text) => text, None => return Ok(()) },
            };
            let status = turn(&mut client, &text, &updates, &mut cancel, &mut quit).await?;
            if *quit.borrow() { return Ok(()); }
            deliver(&updates, &mut quit, Update::Ready(status)).await?;
        }
        Err("Local session turn limit reached. Start a new process; history is not resumed.")
    }.await;
    finish_backend(client, &mut child, result).await
}

fn draw_status(
    frame: &mut ratatui::Frame,
    status: &str,
    transcript: &Transcript,
    viewport: &mut Viewport,
    style: Style,
    border: Style,
    follow: bool,
) {
    let clipped = if transcript.clipped {
        "\nDisplay clipped; backend history unchanged."
    } else {
        ""
    };
    let header = Paragraph::new(format!("{status}\nLocal process history only; quitting ends this session.\np: compose | c: cancel | F6: theme | q / Ctrl+C: quit{clipped}"))
        .style(style).wrap(Wrap { trim: false });
    let block = Block::bordered()
        .title("Local ACP session")
        .border_style(border)
        .title_style(border);
    let inner = block.inner(frame.area());
    frame.render_widget(block, frame.area());
    if inner.width == 0 || inner.height == 0 {
        return;
    }
    let header_height = header
        .line_count(inner.width)
        .min(usize::from(inner.height.saturating_sub(1))) as u16;
    let [header_area, body] = ratatui::layout::Layout::vertical([
        ratatui::layout::Constraint::Length(header_height),
        ratatui::layout::Constraint::Min(0),
    ])
    .areas(inner);
    frame.render_widget(header, header_area);
    let paragraph = Paragraph::new(transcript.text.as_str())
        .style(style)
        .wrap(Wrap { trim: false });
    viewport.measure(paragraph.line_count(body.width), body.height);
    if follow {
        viewport.handle(KeyCode::End);
    }
    frame.render_widget(paragraph.scroll((viewport.offset(), 0)), body);
}

pub async fn run(options: Options) -> Result<(), &'static str> {
    tokio::task::LocalSet::new()
        .run_until(run_ui(options))
        .await
}

async fn run_ui(mut options: Options) -> Result<(), &'static str> {
    let initial = options.prompt.take();
    let (commands, command_rx) = mpsc::channel(1);
    let (update_tx, mut updates) = mpsc::channel(16);
    let (cancel, cancel_rx) = watch::channel(false);
    let (quit, quit_rx) = watch::channel(false);
    let _output = crate::local_runtime::Output::new()?;
    let mut terminal = match ratatui::try_init() {
        Ok(terminal) => terminal,
        Err(_) => {
            let _ = ratatui::try_restore();
            return Err("Cannot initialize local terminal");
        }
    };
    if crate::enable_terminal_input(&mut std::io::stdout()).is_err() {
        let _ = ratatui::try_restore();
        return Err("Cannot enable terminal input");
    }
    let mut worker =
        tokio::task::spawn_local(session(options, command_rx, update_tx, cancel_rx, quit_rx));
    let mut worker_done = false;
    let mut events = EventStream::new();
    let mut composer = Composer::local();
    let mut transcript = Transcript::default();
    let mut viewport = Viewport::default();
    let mut follow = true;
    let mut themes = ThemeSelection::new(
        &std::env::var("AGENT_THEME").unwrap_or_else(|_| "tokyo-night".to_owned()),
        &std::env::var("NO_COLOR").unwrap_or_default(),
    );
    let mut ready = false;
    let mut active = false;
    let mut starting = true;
    let mut status = "Starting local ACP session...".to_owned();
    let mut outcome = Ok(());
    let mut redraw = tokio::time::interval(Duration::from_millis(33));
    redraw.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let result = async {
        loop {
            tokio::select! {
                _ = redraw.tick() => {
            terminal.draw(|frame| {
                if composer.open { composer.draw(frame, themes.style(), themes.border_style()); }
                else { draw_status(frame, &status, &transcript, &mut viewport, themes.style(), themes.border_style(), follow); }
            }).map_err(|_| "Cannot draw terminal")?;
                }
                update = updates.recv(), if !worker_done => match update {
                    Some(Update::Text(text)) => transcript.append(&text),
                    Some(Update::Ready(message)) => {
                        cancel.send_replace(false);
                        ready = true;
                        active = false;
                        status = message.to_owned();
                        transcript.append(&format!("\n{message}\n"));
                        if starting {
                            starting = false;
                            if let Some(text) = initial.as_deref() {
                                commands.try_send(text.to_owned()).map_err(|_| "Local prompt queue unavailable")?;
                                transcript.append(&format!("\nYou: {text}\nAssistant: "));
                                ready = false;
                                active = true;
                                status = "Local turn running... c: cancel".to_owned();
                            } else { composer.open = true; }
                        }
                    }
                    None => {
                        worker_done = true;
                        ready = false;
                        active = false;
                        composer.open = false;
                        outcome = (&mut worker).await.unwrap_or(Err("Local runtime interrupted; no replay."));
                        status = format!("Session closed: {}", outcome.err().unwrap_or("closed"));
                    },
                },
                _ = tokio::signal::ctrl_c() => return Ok(()),
                event = events.next() => {
                    let Some(Ok(event)) = event else { return Err("Terminal input unavailable"); };
                    match event {
                        Event::Paste(text) if composer.open => composer.paste(&text),
                        Event::Mouse(mouse) if !composer.open => { if viewport.mouse(mouse) { follow = false; } }
                        Event::Key(key) if accepts_key_event(key) => {
                            if themes.key(key) { continue; }
                            if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL) { return Ok(()); }
                            if composer.open {
                                if let Some(text) = composer.key(key)
                                    && ready && commands.try_send(text.clone()).is_ok() {
                                        transcript.append(&format!("\nYou: {text}\nAssistant: "));
                                        follow = true;
                                        composer.clear();
                                        composer.open = false;
                                        ready = false;
                                        active = true;
                                        status = "Local turn running... c: cancel".to_owned();
                                }
                                continue;
                            }
                            match key.code {
                                KeyCode::Char('q') => return Ok(()),
                                KeyCode::Char('p') if ready => composer.open = true,
                                KeyCode::Char('c') if active => { cancel.send_replace(true); status = "Canceling local turn; waiting for acknowledgement...".to_owned(); },
                                code => { if viewport.handle(code) { follow = code == KeyCode::End; } }
                            }
                        }
                        _ => {},
                    }
                }
            }
        }
    }.await;
    quit.send_replace(true);
    drop(commands);
    drop(updates);
    let _ = crossterm::execute!(
        std::io::stdout(),
        DisableBracketedPaste,
        DisableMouseCapture
    );
    let _ = ratatui::try_restore();
    if !worker_done {
        outcome = worker
            .await
            .unwrap_or(Err("Local runtime cleanup interrupted"));
    }
    result.and(outcome)
}

#[cfg(test)]
mod tests {
    use super::*;

    // spec: TUI-RUNTIME-R011.14
    #[test]
    fn transcript_is_bounded_unicode_safe_and_inert() {
        let mut transcript = Transcript::default();
        transcript.append(&"界".repeat(TRANSCRIPT_BYTES));
        transcript.append("\u{1b}]52;c;bad\u{7}\u{202e}safe");
        assert!(transcript.text.len() <= TRANSCRIPT_BYTES);
        assert!(transcript.clipped);
        assert!(transcript.text.ends_with("safe"));
        assert!(!transcript.text.contains(['\u{1b}', '\u{7}', '\u{202e}']));
    }

    // spec: TUI-RUNTIME-R011.14
    #[tokio::test]
    async fn quit_interrupts_full_display_queue() {
        let (sender, _receiver) = mpsc::channel(1);
        sender.send(Update::Text("full".to_owned())).await.unwrap();
        let (quit, mut receiver) = watch::channel(false);
        quit.send_replace(true);
        assert!(
            timeout(
                Duration::from_millis(100),
                deliver(&sender, &mut receiver, Update::Ready("blocked"))
            )
            .await
            .unwrap()
            .is_err()
        );
    }
}

#[cfg(test)]
mod backpressure_tests {
    use super::*;
    use agent_terminal_ui_native::acp::TextClient;
    use serde_json::{Value, json};
    use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader, split};

    // spec: TUI-RUNTIME-R011.14
    #[tokio::test]
    async fn cancel_and_quit_drain_the_same_id_when_display_is_full() {
        for quitting in [false, true] {
            let (local, remote) = tokio::io::duplex(4096);
            let (read, write) = split(local);
            let (rr, mut rw) = split(remote);
            let mut reader = BufReader::new(rr);
            let mut client = TextClient::new(read, write).with_sequential_turns();
            let (updates, _display) = mpsc::channel(1);
            updates
                .send(Update::Text("already full".to_owned()))
                .await
                .unwrap();
            let (cancel, mut cancel_rx) = watch::channel(false);
            let (quit, mut quit_rx) = watch::channel(false);
            let backend = async {
                for id in [1, 2] {
                    let mut line = String::new();
                    reader.read_line(&mut line).await.unwrap();
                    let response = if id == 1 {
                        json!({"protocolVersion":1})
                    } else {
                        json!({"sessionId":"session"})
                    };
                    rw.write_all(
                        format!("{}\n", json!({"jsonrpc":"2.0","id":id,"result":response}))
                            .as_bytes(),
                    )
                    .await
                    .unwrap();
                }
                let mut line = String::new();
                reader.read_line(&mut line).await.unwrap();
                let prompt: Value = serde_json::from_str(&line).unwrap();
                assert_eq!(prompt["id"], 3);
                rw.write_all(format!("{}\n", json!({"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"session","update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"blocked"}}}})).as_bytes()).await.unwrap();
                tokio::time::sleep(Duration::from_millis(20)).await;
                if quitting {
                    quit.send_replace(true);
                } else {
                    cancel.send_replace(true);
                }
                line.clear();
                reader.read_line(&mut line).await.unwrap();
                let cancellation: Value = serde_json::from_str(&line).unwrap();
                assert_eq!(cancellation["method"], "session/cancel");
                rw.write_all(
                    b"{\"jsonrpc\":\"2.0\",\"id\":3,\"result\":{\"stopReason\":\"cancelled\"}}\n",
                )
                .await
                .unwrap();
            };
            let frontend = async {
                client.initialize("/workspace").await.unwrap();
                let status = timeout(
                    Duration::from_secs(1),
                    turn(
                        &mut client,
                        "prompt",
                        &updates,
                        &mut cancel_rx,
                        &mut quit_rx,
                    ),
                )
                .await
                .unwrap()
                .unwrap();
                assert!(status.contains("acknowledged"));
                assert_eq!(client.prompt("next").await.unwrap(), 4);
            };
            tokio::join!(backend, frontend);
        }
    }
}
