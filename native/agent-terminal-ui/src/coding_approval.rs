//! Explicit user choices for TUI-RUNTIME-R011. No host effects or policy grants.
use ratatui::{
    Frame,
    layout::Rect,
    widgets::{Block, Paragraph, Wrap},
};
use std::collections::BTreeSet;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Capability {
    ReadText,
    WriteText,
    CreateTerminal,
    TerminalOutput,
    WaitForExit,
    KillTerminal,
}
impl Capability {
    pub fn parse(method: &str) -> Result<Self, ApprovalError> {
        match method {
            "fs/read_text_file" => Ok(Self::ReadText),
            "fs/write_text_file" => Ok(Self::WriteText),
            "terminal/create" => Ok(Self::CreateTerminal),
            "terminal/output" => Ok(Self::TerminalOutput),
            "terminal/wait_for_exit" => Ok(Self::WaitForExit),
            "terminal/kill" => Ok(Self::KillTerminal),
            _ => Err(ApprovalError::CapabilityNotGranted),
        }
    }
    pub fn method(self) -> &'static str {
        match self {
            Self::ReadText => "fs/read_text_file",
            Self::WriteText => "fs/write_text_file",
            Self::CreateTerminal => "terminal/create",
            Self::TerminalOutput => "terminal/output",
            Self::WaitForExit => "terminal/wait_for_exit",
            Self::KillTerminal => "terminal/kill",
        }
    }
}

#[derive(Clone, PartialEq, Eq)]
pub enum RequestContent {
    Write {
        resolved_path: String,
        old_text: String,
        new_text: String,
    },
    Command {
        command: String,
        working_directory: String,
        danger: String,
        command_digest: String,
    },
}
impl RequestContent {
    fn capability(&self) -> Capability {
        match self {
            Self::Write { .. } => Capability::WriteText,
            Self::Command { .. } => Capability::CreateTerminal,
        }
    }
    fn target(&self) -> String {
        match self {
            Self::Write { resolved_path, .. } => resolved_path.clone(),
            Self::Command { command_digest, .. } => command_digest.clone(),
        }
    }
}

/// Construct only from the future authenticated, admitted-session adapter.
/// Equality includes every preview input, including the old file text.
#[derive(Clone, PartialEq, Eq)]
pub struct ApprovalRequest {
    pub session_id: String,
    pub request_id: String,
    pub workspace_root: String,
    pub content: RequestContent,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Choice {
    Approve,
    Deny,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DecisionRecord {
    pub session_id: String,
    pub request_id: String,
    pub method: &'static str,
    pub target: String,
    pub choice: Choice,
    pub actor: String,
}
impl DecisionRecord {
    pub fn text(&self) -> String {
        format!(
            "Session: {}\nRequest: {}\nMethod: {}\nPath or command digest: {}\nDecision: {:?}\nDecided by: {}",
            literal(&self.session_id),
            literal(&self.request_id),
            self.method,
            literal(&self.target),
            self.choice,
            literal(&self.actor)
        )
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ApprovalError {
    CapabilityNotGranted,
    WrongSession,
    RequestChanged,
    PendingRequestExists,
    AlreadyAnswered,
    GatewayUnavailable,
    InvalidMetadata,
}

pub struct ApprovalPreview {
    request: ApprovalRequest,
}
impl ApprovalPreview {
    pub fn text(&self) -> String {
        let request = &self.request;
        let mut text = format!(
            "Session: {}\nRequest: {}\nWorkspace: {}\n",
            literal(&request.session_id),
            literal(&request.request_id),
            literal(&request.workspace_root)
        );
        match &request.content {
            RequestContent::Write {
                resolved_path,
                old_text,
                new_text,
            } => {
                text.push_str(&format!(
                    "Write: {}\n--- before\n+++ after\n@@ -{} +{} @@\n",
                    literal(resolved_path),
                    range(old_text),
                    range(new_text)
                ));
                append_lines(&mut text, '-', old_text);
                append_lines(&mut text, '+', new_text);
            }
            RequestContent::Command {
                command,
                working_directory,
                danger,
                ..
            } => {
                text.push_str(&format!(
                    "Command: {}\nWorking directory: {}\nDanger: {}\n",
                    literal(command),
                    literal(working_directory),
                    literal(danger)
                ));
            }
        }
        text.push_str("Explicit approve or deny required. Closing leaves this request unanswered.");
        text
    }
    pub fn render(&self, frame: &mut Frame<'_>, area: Rect) {
        frame.render_widget(
            Paragraph::new(self.text())
                .wrap(Wrap { trim: false })
                .block(Block::bordered().title("Pending approval")),
            area,
        );
    }
}

pub struct CodingApprovalState {
    session_id: String,
    workspace_root: String,
    capabilities: BTreeSet<Capability>,
    connected: bool,
    pending: Option<ApprovalRequest>,
    records: Vec<DecisionRecord>,
}
impl CodingApprovalState {
    /// Presentation scope only; construction does not establish admission.
    pub fn new(
        session_id: String,
        workspace_root: String,
        capabilities: BTreeSet<Capability>,
    ) -> Self {
        Self {
            session_id,
            workspace_root,
            capabilities,
            connected: false,
            pending: None,
            records: Vec::new(),
        }
    }
    /// Called after the adapter reauthorizes the same session on reconnect.
    pub fn set_connected(&mut self, connected: bool) {
        self.connected = connected;
    }
    pub fn receive(&mut self, request: ApprovalRequest) -> Result<(), ApprovalError> {
        if !self.connected {
            return Err(ApprovalError::GatewayUnavailable);
        }
        if request.session_id != self.session_id || request.workspace_root != self.workspace_root {
            return Err(ApprovalError::WrongSession);
        }
        if request.request_id.is_empty() || request.content.target().is_empty() {
            return Err(ApprovalError::InvalidMetadata);
        }
        if !self.capabilities.contains(&request.content.capability()) {
            return Err(ApprovalError::CapabilityNotGranted);
        }
        if self
            .records
            .iter()
            .any(|r| r.request_id == request.request_id)
        {
            return Err(ApprovalError::AlreadyAnswered);
        }
        if let Some(pending) = &self.pending {
            if pending == &request {
                return Ok(());
            }
            return Err(if pending.request_id == request.request_id {
                ApprovalError::RequestChanged
            } else {
                ApprovalError::PendingRequestExists
            });
        }
        self.pending = Some(request);
        Ok(())
    }
    pub fn preview(&self) -> Option<ApprovalPreview> {
        self.pending
            .clone()
            .map(|request| ApprovalPreview { request })
    }
    pub fn decide(
        &mut self,
        preview: &ApprovalPreview,
        choice: Choice,
        actor: &str,
    ) -> Result<DecisionRecord, ApprovalError> {
        if !self.connected {
            return Err(ApprovalError::GatewayUnavailable);
        }
        if actor.trim().is_empty() {
            return Err(ApprovalError::InvalidMetadata);
        }
        if self.pending.as_ref() != Some(&preview.request) {
            return Err(ApprovalError::RequestChanged);
        }
        let request = &preview.request;
        let record = DecisionRecord {
            session_id: request.session_id.clone(),
            request_id: request.request_id.clone(),
            method: request.content.capability().method(),
            target: request.content.target(),
            choice,
            actor: actor.to_owned(),
        };
        self.records.push(record.clone());
        self.pending = None;
        Ok(record)
    }
    pub fn records(&self) -> &[DecisionRecord] {
        &self.records
    }
}
fn literal(value: &str) -> String {
    value
        .chars()
        .flat_map(|c| {
            if c.is_control() {
                c.escape_default().collect::<Vec<_>>()
            } else {
                vec![c]
            }
        })
        .collect()
}
fn range(value: &str) -> String {
    let count = value.split_terminator('\n').count();
    if count == 0 {
        "0,0".into()
    } else {
        format!("1,{count}")
    }
}
fn append_lines(output: &mut String, prefix: char, text: &str) {
    for line in text.split_terminator('\n') {
        output.push_str(&format!("{prefix}{}\n", literal(line)));
    }
    if !text.is_empty() && !text.ends_with('\n') {
        output.push_str("\\ No newline at end of file\n");
    }
}
