//! Narrow ACP v1 text transport. Authority and agent execution remain in Arbora.
use serde_json::{Value, json};
use tokio::io::{AsyncBufReadExt, AsyncRead, AsyncWrite, AsyncWriteExt, BufReader};

pub const MAX_FRAME_BYTES: usize = 256 * 1024;
pub const MAX_OUTPUT_BYTES: usize = 4 * 1024 * 1024;

pub struct TextClient<R, W> {
    reader: BufReader<R>,
    writer: W,
    frame: Vec<u8>,
    session: Option<String>,
    output_bytes: usize,
    close_supported: bool,
    pending: Option<u64>,
    notifications: usize,
    prompted: bool,
    sequential: bool,
    next_id: u64,
    turn: Option<u64>,
    turn_ready: bool,
}

impl<R: AsyncRead + Unpin, W: AsyncWrite + Unpin> TextClient<R, W> {
    pub fn new(reader: R, writer: W) -> Self {
        Self {
            reader: BufReader::new(reader),
            writer,
            frame: Vec::new(),
            session: None,
            output_bytes: 0,
            close_supported: false,
            pending: None,
            notifications: 0,
            prompted: false,
            sequential: false,
            next_id: 3,
            turn: None,
            turn_ready: true,
        }
    }

    pub fn with_sequential_turns(mut self) -> Self {
        self.sequential = true;
        self
    }

    async fn send(&mut self, value: Value) -> Result<(), &'static str> {
        let mut bytes = serde_json::to_vec(&value).map_err(|_| "Invalid ACP request")?;
        if bytes.len() > 64 * 1024 {
            return Err("ACP request exceeds frame limit");
        }
        bytes.push(b'\n');
        self.writer
            .write_all(&bytes)
            .await
            .map_err(|_| "ACP write failed")?;
        self.writer.flush().await.map_err(|_| "ACP flush failed")
    }

    async fn read(&mut self) -> Result<Value, &'static str> {
        loop {
            let available = self
                .reader
                .fill_buf()
                .await
                .map_err(|_| "ACP read failed")?;
            if available.is_empty() {
                return Err("ACP closed before a complete response; outcome unknown");
            }
            let end = available.iter().position(|byte| *byte == b'\n');
            let count = end.map_or(available.len(), |index| index + 1);
            if self.frame.len() + count > MAX_FRAME_BYTES {
                return Err("ACP response exceeds frame limit");
            }
            self.frame.extend_from_slice(&available[..count]);
            self.reader.consume(count);
            if end.is_some() {
                let value =
                    serde_json::from_slice(&self.frame).map_err(|_| "Invalid ACP JSON frame");
                self.frame.clear();
                return value;
            }
        }
    }

    async fn request(&mut self, id: u64, method: &str, params: Value) -> Result<(), &'static str> {
        if self.pending.is_some() {
            return Err("ACP request already pending");
        }
        self.send(json!({"jsonrpc":"2.0","id":id,"method":method,"params":params}))
            .await?;
        self.pending = Some(id);
        Ok(())
    }

    /// Cancellation-safe: partially read frames live on the client, not this future.
    pub async fn response(
        &mut self,
        id: u64,
        mut output: impl AsyncFnMut(&str) -> Result<(), &'static str>,
    ) -> Result<Value, &'static str> {
        if self.pending != Some(id) {
            return Err("ACP response was not requested");
        }
        loop {
            let value = self.read().await?;
            if value.get("jsonrpc").and_then(Value::as_str) != Some("2.0") || !value.is_object() {
                return Err("Invalid ACP envelope");
            }
            if let Some(method) = value.get("method") {
                self.notifications += 1;
                if self.notifications > 16_384 {
                    return Err("ACP notification limit");
                }
                if value.get("result").is_some() || value.get("error").is_some() {
                    return Err("Invalid ACP method envelope");
                }
                if let Some(request_id) = value.get("id") {
                    if !request_id.is_string() && request_id.as_i64().is_none() {
                        return Err("Invalid ACP callback identifier");
                    }
                    // No advertised capabilities confer authority to perform host effects.
                    if method == "session/request_permission" {
                        self.send(json!({"jsonrpc":"2.0","id":request_id,"result":{"outcome":{"outcome":"cancelled"}}})).await?;
                    } else {
                        self.send(json!({"jsonrpc":"2.0","id":request_id,"error":{"code":-32601,"message":"Client capability unavailable"}})).await?;
                    }
                    return Err(
                        "ACP requested an unsupported client capability; no permission granted",
                    );
                }
                if method != "session/update" {
                    return Err("Unsupported ACP notification");
                }
                let params = &value["params"];
                if self.session.as_deref().is_none()
                    || params["sessionId"].as_str() != self.session.as_deref()
                {
                    return Err("Foreign ACP session update");
                }
                let update = &params["update"];
                if update["sessionUpdate"] != "agent_message_chunk"
                    || update["content"]["type"] != "text"
                {
                    return Err("Unsupported ACP session update");
                }
                let text = update["content"]["text"]
                    .as_str()
                    .ok_or("Invalid ACP text update")?;
                self.output_bytes = self
                    .output_bytes
                    .checked_add(text.len())
                    .ok_or("ACP output limit")?;
                if self.output_bytes > MAX_OUTPUT_BYTES {
                    return Err("ACP output limit");
                }
                output(text).await?;
                continue;
            }
            if value.get("id").and_then(Value::as_u64) != Some(id)
                || value.get("result").is_some() == value.get("error").is_some()
            {
                return Err("Mismatched ACP response");
            }
            self.pending = None;
            if value.get("error").is_some() {
                return Err("Arbora ACP refused the request; no automatic retry");
            }
            let result = value
                .get("result")
                .filter(|result| result.is_object())
                .ok_or("Invalid ACP result")?;
            if self.turn == Some(id) {
                self.turn_ready = matches!(
                    result["stopReason"].as_str(),
                    Some("end_turn" | "cancelled")
                );
            }
            return Ok(result.clone());
        }
    }

    pub async fn initialize(&mut self, cwd: &str) -> Result<(), &'static str> {
        if self.session.is_some() {
            return Err("ACP session already initialized");
        }
        if !std::path::Path::new(cwd).is_absolute() {
            return Err("ACP workspace must be absolute");
        }
        self.request(1, "initialize", json!({"protocolVersion":1,"clientCapabilities":{},"clientInfo":{"name":"tuig","version":env!("CARGO_PKG_VERSION")}})).await?;
        let initialized = self
            .response(1, async |_| {
                Err("Unexpected ACP output during initialization")
            })
            .await?;
        if initialized["protocolVersion"] != 1 {
            return Err("Unsupported ACP protocol version");
        }
        self.close_supported =
            initialized["agentCapabilities"]["sessionCapabilities"]["close"].is_object();
        self.request(2, "session/new", json!({"cwd":cwd,"mcpServers":[]}))
            .await?;
        let created = self
            .response(2, async |_| {
                Err("Unexpected ACP output before session creation")
            })
            .await?;
        let session = created["sessionId"]
            .as_str()
            .filter(|id| !id.is_empty() && id.len() <= 4096)
            .ok_or("Invalid ACP session identifier")?;
        self.session = Some(session.to_owned());
        Ok(())
    }

    pub async fn idle(&mut self) -> Result<(), &'static str> {
        if self.pending.is_some() {
            return Err("ACP request still pending");
        }
        let result = self.read().await;
        self.turn_ready = false;
        result?;
        Err("Unsolicited ACP message between turns")
    }

    pub async fn prompt(&mut self, text: &str) -> Result<u64, &'static str> {
        if self.prompted && !self.sequential {
            return Err("ACP one-shot prompt already sent");
        }
        if !self.frame.is_empty() {
            return Err("Partial unsolicited ACP frame; session cannot continue");
        }
        if !self.turn_ready {
            return Err("ACP previous turn has no acknowledged outcome");
        }
        if text.trim().is_empty() || text.len() > 16_384 {
            return Err("ACP prompt must contain 1..16384 bytes");
        }
        let session = self
            .session
            .as_deref()
            .ok_or("ACP session not initialized")?;
        let id = self.next_id;
        self.next_id = self.next_id.checked_add(1).ok_or("ACP request ID limit")?;
        self.turn_ready = false;
        self.output_bytes = 0;
        self.notifications = 0;
        self.request(
            id,
            "session/prompt",
            json!({"sessionId":session,"prompt":[{"type":"text","text":text}]}),
        )
        .await?;
        self.prompted = true;
        self.turn = Some(id);
        Ok(id)
    }

    pub async fn cancel(&mut self) -> Result<(), &'static str> {
        let session = self
            .session
            .as_deref()
            .ok_or("ACP session not initialized")?;
        self.send(json!({"jsonrpc":"2.0","method":"session/cancel","params":{"sessionId":session}}))
            .await
    }

    pub async fn close(&mut self) -> Result<(), &'static str> {
        if self.close_supported {
            let session = self
                .session
                .as_deref()
                .ok_or("ACP session not initialized")?;
            let id = self.next_id;
            self.next_id = self.next_id.checked_add(1).ok_or("ACP request ID limit")?;
            self.request(id, "session/close", json!({"sessionId":session}))
                .await?;
            self.response(id, async |_| Err("Unexpected ACP output after turn"))
                .await?;
        }
        self.writer
            .shutdown()
            .await
            .map_err(|_| "ACP shutdown failed")
    }
}

pub fn completed(result: &Value) -> Result<(), &'static str> {
    match result["stopReason"].as_str() {
        Some("end_turn") => Ok(()),
        Some("cancelled") => Err("Local ACP turn canceled"),
        _ => Err("Local ACP turn did not complete successfully"),
    }
}
