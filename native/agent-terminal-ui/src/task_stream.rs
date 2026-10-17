//! Bounded SSE consumption for an already-bound task, without transport effects.
use crate::correlation::{TaskCorrelation, TaskEvent};
use serde_json::Value;

pub const MAX_LINE_BYTES: usize = 16 * 1024;
pub const MAX_EVENT_BYTES: usize = 256 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StreamError {
    Limit,
    InvalidUtf8,
    InvalidEnvelope,
    Refused,
    Correlation,
    InvalidCursor,
    Truncated,
    Stopped,
}

#[derive(Debug, PartialEq, Eq)]
pub struct StreamEvent {
    pub event: TaskEvent,
    pub cursor: Option<String>,
}

pub struct TaskStreamDecoder {
    request_id: String,
    binding: TaskCorrelation,
    line: Vec<u8>,
    data: String,
    has_data: bool,
    pending_cursor: Option<String>,
    cursor: Option<String>,
    event_bytes: usize,
    after_cr: bool,
    first_line: bool,
    stopped: bool,
}

impl TaskStreamDecoder {
    pub fn new(request_id: String, binding: TaskCorrelation) -> Result<Self, StreamError> {
        if request_id.is_empty() || request_id.len() > MAX_LINE_BYTES {
            return Err(StreamError::InvalidEnvelope);
        }
        Ok(Self {
            request_id,
            binding,
            line: Vec::new(),
            data: String::new(),
            has_data: false,
            pending_cursor: None,
            cursor: None,
            event_bytes: 0,
            after_cr: false,
            first_line: true,
            stopped: false,
        })
    }

    pub fn cursor(&self) -> Option<&str> {
        self.cursor.as_deref()
    }

    /// Deliver validated events immediately; an error stops subsequent input.
    /// Events delivered before an error in the same chunk remain accepted.
    pub fn feed(
        &mut self,
        bytes: &[u8],
        mut accept: impl FnMut(StreamEvent),
    ) -> Result<(), StreamError> {
        if self.stopped {
            return Err(StreamError::Stopped);
        }
        for &byte in bytes {
            match self.byte(byte) {
                Ok(Some(event)) => accept(event),
                Ok(None) => {}
                Err(error) => {
                    self.stopped = true;
                    self.line.clear();
                    self.data.clear();
                    self.pending_cursor = None;
                    return Err(error);
                }
            }
        }
        Ok(())
    }

    /// EOF never promotes an unterminated event into accepted state.
    pub fn finish(&mut self) -> Result<(), StreamError> {
        if self.stopped {
            return Err(StreamError::Stopped);
        }
        self.stopped = true;
        if !self.line.is_empty() || self.has_data {
            return Err(StreamError::Truncated);
        }
        Ok(())
    }

    fn byte(&mut self, byte: u8) -> Result<Option<StreamEvent>, StreamError> {
        self.event_bytes += 1;
        if self.event_bytes > MAX_EVENT_BYTES {
            return Err(StreamError::Limit);
        }
        if self.after_cr {
            self.after_cr = false;
            if byte == b'\n' {
                return Ok(None);
            }
        }
        if byte == b'\r' || byte == b'\n' {
            self.after_cr = byte == b'\r';
            return self.end_line();
        }
        if self.line.len() == MAX_LINE_BYTES {
            return Err(StreamError::Limit);
        }
        self.line.push(byte);
        Ok(None)
    }

    fn end_line(&mut self) -> Result<Option<StreamEvent>, StreamError> {
        if self.first_line {
            self.first_line = false;
            if self.line.starts_with(&[0xef, 0xbb, 0xbf]) {
                self.line.drain(..3);
            }
        }
        if self.line.is_empty() {
            let event = if self.has_data {
                Some(self.validate_event()?)
            } else {
                None
            };
            self.data.clear();
            self.has_data = false;
            self.event_bytes = 0;
            return Ok(event);
        }
        let line = std::str::from_utf8(&self.line).map_err(|_| StreamError::InvalidUtf8)?;
        let (field, value) = line.split_once(':').unwrap_or((line, ""));
        let value = value.strip_prefix(' ').unwrap_or(value);
        match field {
            "data" => {
                if self.has_data {
                    self.data.push('\n');
                }
                self.data.push_str(value);
                self.has_data = true;
            }
            "id" => {
                if value.contains('\0') {
                    return Err(StreamError::InvalidCursor);
                }
                self.pending_cursor = Some(value.to_owned());
            }
            _ => {}
        }
        self.line.clear();
        Ok(None)
    }

    fn validate_event(&mut self) -> Result<StreamEvent, StreamError> {
        let envelope: Value =
            serde_json::from_str(&self.data).map_err(|_| StreamError::InvalidEnvelope)?;
        if envelope.get("jsonrpc").and_then(Value::as_str) != Some("2.0")
            || envelope.get("id").and_then(Value::as_str) != Some(&self.request_id)
        {
            return Err(StreamError::InvalidEnvelope);
        }
        if envelope.get("error").is_some() {
            return Err(if envelope.get("result").is_some() {
                StreamError::InvalidEnvelope
            } else {
                StreamError::Refused
            });
        }
        let result = envelope.get("result").ok_or(StreamError::InvalidEnvelope)?;
        let event = self
            .binding
            .validate(result)
            .map_err(|_| StreamError::Correlation)?;
        if let Some(cursor) = &self.pending_cursor {
            self.cursor = Some(cursor.clone());
        }
        Ok(StreamEvent {
            event,
            cursor: self.cursor.clone(),
        })
    }
}
