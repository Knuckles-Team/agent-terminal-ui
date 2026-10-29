//! Bounded, public flat-plan projection. Node identifiers grant no child authority.
use crate::{
    ArboraClient, correlation::TaskCorrelation, public_run_events::literal,
    run_inspector::ReadRefusal,
};
use serde_json::{Value, json};
use std::collections::{HashMap, HashSet};

pub const SCHEMA: &str = "arbora-execution-graph-v1";
pub const MAX_NODES: usize = 64;
pub const MAX_EDGES: usize = 2016;
pub const MAX_EVENTS: u64 = 1000;
pub const MAX_KEY_CHARS: usize = 16384;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StepEvidence {
    pub event_id: String,
    pub sequence: u64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExecutionStep {
    pub key: String,
    pub task_id: String,
    pub status: String,
    pub evidence: Option<StepEvidence>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExecutionGraph {
    pub run_id: String,
    pub task_id: String,
    pub plan_digest: String,
    pub nodes: Vec<ExecutionStep>,
    /// Each pair is (predecessor, dependent), never a spawn relationship.
    pub edges: Vec<(usize, usize)>,
    pub covered_after: u64,
    pub has_more: bool,
}

fn exact(value: &Value, fields: &[&str]) -> Result<(), ReadRefusal> {
    let object = value.as_object().ok_or(ReadRefusal::Unavailable)?;
    if object.len() != fields.len() || fields.iter().any(|field| !object.contains_key(*field)) {
        return Err(ReadRefusal::Unavailable);
    }
    Ok(())
}

fn identifier(value: &Value, maximum: usize) -> Result<&str, ReadRefusal> {
    value
        .as_str()
        .filter(|s| !s.trim().is_empty() && s.chars().count() <= maximum)
        .ok_or(ReadRefusal::Unavailable)
}

fn label(value: &str) -> String {
    // Opaque identities stay unchanged; only their single-line labels are sanitized.
    literal(value).replace(['\n', '\t'], " ")
}

fn key(value: &Value, run_id: &str) -> Result<String, ReadRefusal> {
    let encoded = identifier(value, MAX_KEY_CHARS)?;
    // JSON escape spelling is not identity: Python emits ASCII Unicode escapes.
    let parts: [String; 3] = serde_json::from_str(encoded).map_err(|_| ReadRefusal::Unavailable)?;
    if parts[0] != run_id || parts[1] != "plan_step" {
        return Err(ReadRefusal::Unavailable);
    }
    identifier(&Value::String(parts[2].clone()), 512)?;
    Ok(parts[2].clone())
}

impl ExecutionGraph {
    pub fn decode(value: &Value, binding: &TaskCorrelation) -> Result<Self, ReadRefusal> {
        let run_id = binding.run_id().ok_or(ReadRefusal::Unavailable)?;
        for id in [run_id, binding.task_id(), binding.context_id()] {
            identifier(&json!(id), 512)?;
        }
        exact(
            value,
            &[
                "schema_version",
                "availability",
                "run_id",
                "task_id",
                "snapshot",
            ],
        )?;
        if value["schema_version"].as_str() != Some(SCHEMA) {
            return Err(ReadRefusal::Unavailable);
        }
        if value["run_id"].as_str() != Some(run_id)
            || value["task_id"].as_str() != Some(binding.task_id())
        {
            return Err(ReadRefusal::WrongRun);
        }
        if value["availability"].as_str() != Some("available") {
            return Err(ReadRefusal::Unavailable);
        }
        let snapshot = &value["snapshot"];
        exact(
            snapshot,
            &[
                "plan_digest",
                "nodes",
                "edges",
                "topology_completeness",
                "lifecycle_completeness",
                "lifecycle_reason",
                "covered_after",
                "has_more",
                "can_read_transcript",
                "can_message_active",
                "can_continue_completed",
                "supports_spawned_children",
            ],
        )?;
        if snapshot["topology_completeness"].as_str() != Some("complete")
            || snapshot["lifecycle_completeness"].as_str() != Some("incomplete")
            || snapshot["lifecycle_reason"].as_str() != Some("observed_prefix_only")
            || [
                "can_read_transcript",
                "can_message_active",
                "can_continue_completed",
                "supports_spawned_children",
            ]
            .iter()
            .any(|field| snapshot[field].as_bool() != Some(false))
        {
            return Err(ReadRefusal::Unavailable);
        }
        let plan_digest = identifier(&snapshot["plan_digest"], 512)?.to_owned();
        let covered_after = snapshot["covered_after"]
            .as_u64()
            .filter(|n| *n <= MAX_EVENTS)
            .ok_or(ReadRefusal::Unavailable)?;
        let has_more = snapshot["has_more"]
            .as_bool()
            .ok_or(ReadRefusal::Unavailable)?;
        let raw_nodes = snapshot["nodes"]
            .as_array()
            .filter(|nodes| !nodes.is_empty() && nodes.len() <= MAX_NODES)
            .ok_or(ReadRefusal::Unavailable)?;
        let raw_edges = snapshot["edges"]
            .as_array()
            .filter(|edges| edges.len() <= MAX_EDGES)
            .ok_or(ReadRefusal::Unavailable)?;
        let mut ids = HashMap::new();
        let mut events = HashSet::new();
        let mut sequences = HashSet::new();
        let mut nodes = Vec::new();
        for node in raw_nodes {
            exact(node, &["key", "kind", "task_id", "status", "evidence"])?;
            let task_id = identifier(&node["task_id"], 512)?;
            let status = node["status"].as_str().ok_or(ReadRefusal::Unavailable)?;
            if node["kind"].as_str() != Some("plan_step")
                || key(&node["key"], run_id)? != task_id
                || ids.insert(task_id.to_owned(), nodes.len()).is_some()
                || !matches!(
                    status,
                    "unobserved" | "running" | "completed" | "failed" | "cancelled" | "blocked"
                )
            {
                return Err(ReadRefusal::Unavailable);
            }
            let evidence = if node["evidence"].is_null() {
                if status != "unobserved" {
                    return Err(ReadRefusal::Unavailable);
                }
                None
            } else {
                let evidence = &node["evidence"];
                exact(evidence, &["event_id", "sequence"])?;
                let event_id = identifier(&evidence["event_id"], 1024)?.to_owned();
                let sequence = evidence["sequence"]
                    .as_u64()
                    .filter(|n| *n > 0 && *n <= covered_after)
                    .ok_or(ReadRefusal::Unavailable)?;
                if status == "unobserved"
                    || !events.insert(event_id.clone())
                    || !sequences.insert(sequence)
                {
                    return Err(ReadRefusal::Unavailable);
                }
                Some(StepEvidence { event_id, sequence })
            };
            nodes.push(ExecutionStep {
                key: node["key"]
                    .as_str()
                    .ok_or(ReadRefusal::Unavailable)?
                    .to_owned(),
                task_id: task_id.to_owned(),
                status: status.to_owned(),
                evidence,
            });
        }
        let mut edges = Vec::new();
        let mut unique = HashSet::new();
        let mut incoming = vec![0; nodes.len()];
        for edge in raw_edges {
            exact(edge, &["kind", "source", "target"])?;
            let source = *ids
                .get(&key(&edge["source"], run_id)?)
                .ok_or(ReadRefusal::Unavailable)?;
            let target = *ids
                .get(&key(&edge["target"], run_id)?)
                .ok_or(ReadRefusal::Unavailable)?;
            if edge["kind"].as_str() != Some("depends_on")
                || source == target
                || !unique.insert((source, target))
            {
                return Err(ReadRefusal::Unavailable);
            }
            incoming[target] += 1;
            edges.push((source, target));
        }
        let mut ready: Vec<_> = incoming
            .iter()
            .enumerate()
            .filter_map(|(i, count)| (*count == 0).then_some(i))
            .collect();
        let mut visited = 0;
        while let Some(source) = ready.pop() {
            visited += 1;
            for &(_, target) in edges.iter().filter(|(from, _)| *from == source) {
                incoming[target] -= 1;
                if incoming[target] == 0 {
                    ready.push(target);
                }
            }
        }
        if visited != nodes.len() {
            return Err(ReadRefusal::Unavailable);
        }
        Ok(Self {
            run_id: run_id.to_owned(),
            task_id: binding.task_id().to_owned(),
            plan_digest,
            nodes,
            edges,
            covered_after,
            has_more,
        })
    }

    pub fn text(&self, selected: usize) -> String {
        let mut lines = vec![
            "Flat execution DAG (read-only)".to_owned(),
            format!("Run: {}", label(&self.run_id)),
            format!("Root task: {}", label(&self.task_id)),
            format!("Plan: {}", label(&self.plan_digest)),
            "Topology: complete".to_owned(),
            "Lifecycle: incomplete; observed prefix only".to_owned(),
            format!(
                "Covered cursor: {} | more: {}",
                self.covered_after, self.has_more
            ),
            "Unobserved means unknown, not pending.".to_owned(),
            "".to_owned(),
            "Steps (Tab / Shift+Tab: select)".to_owned(),
        ];
        for (index, node) in self.nodes.iter().enumerate() {
            lines.push(format!(
                "{}{}. {} [{}]",
                if index == selected { "> " } else { "  " },
                index + 1,
                label(&node.task_id),
                node.status
            ));
        }
        if let Some(node) = self.nodes.get(selected) {
            let adjacent = |predecessors| {
                let indices: Vec<_> = self
                    .edges
                    .iter()
                    .filter_map(|&(from, to)| {
                        if predecessors && to == selected {
                            Some(from)
                        } else if !predecessors && from == selected {
                            Some(to)
                        } else {
                            None
                        }
                    })
                    .map(|index| format!("{}: {}", index + 1, label(&self.nodes[index].task_id)))
                    .collect();
                if indices.is_empty() {
                    "none".to_owned()
                } else {
                    indices.join(", ")
                }
            };
            lines.extend([
                "".to_owned(),
                "Selected step details".to_owned(),
                format!("Predecessors (depends_on): {}", adjacent(true)),
                format!("Dependents (depends_on): {}", adjacent(false)),
                node.evidence.as_ref().map_or_else(
                    || "Public event evidence: unavailable".to_owned(),
                    |e| {
                        format!(
                            "Public event evidence: {} (sequence {})",
                            label(&e.event_id),
                            e.sequence
                        )
                    },
                ),
            ]);
        }
        lines.extend([
            "".to_owned(),
            "Spawned children: unsupported".to_owned(),
            "Transcript: unavailable".to_owned(),
            "Message active child: unavailable".to_owned(),
            "Continue completed child: unavailable".to_owned(),
        ]);
        lines.join("\n")
    }
}

impl ArboraClient {
    /// The root binding is validated task data, never a run-local step or graph key.
    pub async fn get_execution_graph(
        &self,
        binding: &TaskCorrelation,
    ) -> Result<ExecutionGraph, ReadRefusal> {
        let run = binding.run_id().ok_or(ReadRefusal::Unavailable)?;
        for id in [run, binding.task_id(), binding.context_id()] {
            identifier(&json!(id), 512)?;
        }
        let value = self
            .read_run_operation(
                "runs.execution_graph",
                run,
                json!({
                    "schema_version": SCHEMA, "run_id": run, "task_id": binding.task_id()
                }),
            )
            .await?;
        ExecutionGraph::decode(&value, binding)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> Value {
        serde_json::from_str(include_str!(
            "../tests/fixtures/execution_graph_contract.json"
        ))
        .unwrap()
    }

    fn binding(value: &Value) -> TaskCorrelation {
        TaskCorrelation::from_task(&json!({
            "kind": "task", "id": value["task_id"], "contextId": "context-one",
            "status": {"state": "working"}, "metadata": {"arbora": {"runId": value["run_id"]}}
        }))
        .unwrap()
    }

    // spec: TUIG-RUNTIME-R010.11, TUIG-RUNTIME-R010.12
    #[test]
    fn producer_diamond_and_unicode_are_semantic_keys_not_serialization_spellings() {
        let fixture = fixture();
        for field in ["value", "unicode_value", "max_unicode_value"] {
            let value = &fixture[field];
            let graph = ExecutionGraph::decode(value, &binding(value)).unwrap();
            assert_eq!(
                graph.nodes.len(),
                value["snapshot"]["nodes"].as_array().unwrap().len()
            );
            assert_eq!(graph.nodes[0].key, value["snapshot"]["nodes"][0]["key"]);
            let mut equivalent = value.clone();
            for node in equivalent["snapshot"]["nodes"].as_array_mut().unwrap() {
                let tuple: Value = serde_json::from_str(node["key"].as_str().unwrap()).unwrap();
                node["key"] = json!(tuple.to_string());
            }
            let decoded = ExecutionGraph::decode(&equivalent, &binding(value)).unwrap();
            assert_eq!(decoded.edges, graph.edges);
            assert_eq!(decoded.nodes[0].task_id, graph.nodes[0].task_id);
        }
        let graph = ExecutionGraph::decode(&fixture["value"], &binding(&fixture["value"])).unwrap();
        assert_eq!(graph.edges, vec![(0, 1), (0, 2), (1, 3), (2, 3)]);
        assert_eq!(graph.text(3).matches("4. join [unobserved]").count(), 1);
        assert!(
            graph
                .text(3)
                .contains("Predecessors (depends_on): 2: left, 3: right")
        );
        assert!(
            graph
                .text(0)
                .contains("Dependents (depends_on): 2: left, 3: right")
        );
        assert!(graph.text(0).contains("event-2 (sequence 2)"));
        assert!(
            graph
                .text(3)
                .contains("Unobserved means unknown, not pending")
        );
        assert!(graph.text(3).contains("Message active child: unavailable"));
    }

    // spec: TUIG-RUNTIME-R010.11, TUIG-RUNTIME-R010.12
    #[test]
    fn opaque_control_and_markup_ids_keep_identity_but_render_inertly() {
        let mut value = fixture()["value"].clone();
        let bound = binding(&value);
        let opaque = "\u{1b}[31m[bold]step\n> forged\t\u{202e}end";
        let evidence = "event\u{1b}]52;c;private\u{7}\n[link]";
        let encoded = json!([value["run_id"], "plan_step", opaque]).to_string();
        let old_key = value["snapshot"]["nodes"][0]["key"].clone();
        value["snapshot"]["nodes"][0]["task_id"] = json!(opaque);
        value["snapshot"]["nodes"][0]["key"] = json!(encoded);
        value["snapshot"]["nodes"][0]["evidence"]["event_id"] = json!(evidence);
        value["snapshot"]["plan_digest"] = json!(opaque);
        for edge in value["snapshot"]["edges"].as_array_mut().unwrap() {
            if edge["source"] == old_key {
                edge["source"] = json!(encoded);
            }
        }
        let graph = ExecutionGraph::decode(&value, &bound).unwrap();
        assert_eq!(graph.nodes[0].key, encoded);
        assert_eq!(graph.nodes[0].task_id, opaque);
        assert_eq!(graph.nodes[0].evidence.as_ref().unwrap().event_id, evidence);
        assert_eq!(graph.edges, vec![(0, 1), (0, 2), (1, 3), (2, 3)]);
        let text = graph.text(0);
        assert!(!text.contains('\u{1b}'));
        assert!(!text.contains('\u{7}'));
        assert!(!text.contains('\u{202e}'));
        assert!(!text.contains("\n> forged"));
        assert!(text.contains("[bold]step > forged end"));
        assert!(text.contains("[link]"));
    }

    // spec: TUIG-RUNTIME-R010.11
    #[test]
    fn native_bounds_and_fields_match_actual_producer_schema() {
        let fixture = fixture();
        let schema = &fixture["schema"];
        assert_eq!(
            schema["params"]["properties"]["schema_version"]["const"],
            SCHEMA
        );
        let defs = &schema["result"]["$defs"];
        let snapshot = &defs["ExecutionGraphSnapshot"]["properties"];
        assert_eq!(snapshot["nodes"]["maxItems"], MAX_NODES);
        assert_eq!(snapshot["edges"]["maxItems"], MAX_EDGES);
        assert_eq!(snapshot["covered_after"]["maximum"], MAX_EVENTS);
        assert_eq!(
            defs["ExecutionStep"]["properties"]["key"]["maxLength"],
            MAX_KEY_CHARS
        );
        for capability in [
            "can_read_transcript",
            "can_message_active",
            "can_continue_completed",
            "supports_spawned_children",
        ] {
            assert_eq!(snapshot[capability]["const"], false);
        }
        for kind in [
            "ExecutionGraphRead",
            "ExecutionGraphSnapshot",
            "ExecutionStep",
            "StepEvidence",
            "ExecutionDependency",
        ] {
            assert_eq!(defs[kind]["additionalProperties"], false);
        }
    }

    // spec: TUIG-RUNTIME-R010.11
    #[test]
    fn malformed_private_wrong_owner_and_unsupported_projections_fail_closed() {
        let value = fixture()["value"].clone();
        let bound = binding(&value);
        for (pointer, invalid) in [
            ("/schema_version", json!("arbora-execution-graph-v2")),
            ("/run_id", json!("other-run")),
            ("/task_id", json!("first")),
            ("/availability", json!("unavailable")),
            ("/snapshot", Value::Null),
            ("/snapshot/covered_after", json!(true)),
            ("/snapshot/covered_after", json!(1.0)),
            ("/snapshot/covered_after", json!(-1)),
            ("/snapshot/covered_after", json!(1001)),
            ("/snapshot/has_more", json!(0)),
            ("/snapshot/nodes", json!([])),
            ("/snapshot/topology_completeness", json!("partial")),
            ("/snapshot/lifecycle_completeness", json!("complete")),
            ("/snapshot/lifecycle_reason", json!("finished")),
            ("/snapshot/can_read_transcript", json!(true)),
            ("/snapshot/can_message_active", json!(true)),
            ("/snapshot/can_continue_completed", json!(true)),
            ("/snapshot/supports_spawned_children", json!(true)),
            ("/snapshot/nodes/0/status", json!("pending")),
            ("/snapshot/nodes/0/evidence", Value::Null),
            ("/snapshot/nodes/0/evidence/sequence", json!(true)),
            ("/snapshot/nodes/0/evidence/sequence", json!(3)),
            (
                "/snapshot/nodes/0/key",
                json!("[\"run-one\",\"child\",\"first\"]"),
            ),
            ("/snapshot/edges/0/kind", json!("spawned_child")),
            (
                "/snapshot/edges/0/target",
                json!("[\"run-one\",\"plan_step\",\"missing\"]"),
            ),
        ] {
            let mut malformed = value.clone();
            *malformed.pointer_mut(pointer).unwrap() = invalid;
            assert!(
                ExecutionGraph::decode(&malformed, &bound).is_err(),
                "{pointer}"
            );
        }
        for pointer in [
            "",
            "/snapshot",
            "/snapshot/nodes/0",
            "/snapshot/nodes/0/evidence",
            "/snapshot/edges/0",
        ] {
            let mut private = value.clone();
            private
                .pointer_mut(pointer)
                .unwrap()
                .as_object_mut()
                .unwrap()
                .insert("private_thought".to_owned(), json!("not public"));
            assert!(ExecutionGraph::decode(&private, &bound).is_err());
        }
    }

    // spec: TUIG-RUNTIME-R010.11
    #[test]
    fn duplicates_cycles_evidence_reuse_and_bounds_are_rejected() {
        let value = fixture()["value"].clone();
        let bound = binding(&value);
        let mut cases = Vec::new();
        let mut equivalent = value.clone();
        equivalent["snapshot"]["nodes"][1] = equivalent["snapshot"]["nodes"][0].clone();
        equivalent["snapshot"]["nodes"][1]["key"] =
            json!("[ \"run-one\", \"plan_step\", \"first\" ]");
        cases.push(equivalent);
        let mut duplicate = value.clone();
        duplicate["snapshot"]["nodes"][1] = duplicate["snapshot"]["nodes"][0].clone();
        cases.push(duplicate);
        let mut duplicate = value.clone();
        duplicate["snapshot"]["edges"][1] = duplicate["snapshot"]["edges"][0].clone();
        cases.push(duplicate);
        let mut cycle = value.clone();
        let source = cycle["snapshot"]["nodes"][3]["key"].clone();
        let target = cycle["snapshot"]["nodes"][0]["key"].clone();
        cycle["snapshot"]["edges"]
            .as_array_mut()
            .unwrap()
            .push(json!({"kind":"depends_on","source":source,"target":target}));
        cases.push(cycle);
        for reused_event in [false, true] {
            let mut reused = value.clone();
            reused["snapshot"]["nodes"][1]["status"] = json!("completed");
            reused["snapshot"]["nodes"][1]["evidence"] = if reused_event {
                json!({"event_id":"event-2", "sequence":1})
            } else {
                json!({"event_id":"different-event", "sequence":2})
            };
            cases.push(reused);
        }
        for (field, count) in [("nodes", MAX_NODES + 1), ("edges", MAX_EDGES + 1)] {
            let mut oversized = value.clone();
            oversized["snapshot"][field] =
                json!(vec![oversized["snapshot"][field][0].clone(); count]);
            cases.push(oversized);
        }
        for invalid in cases {
            assert!(ExecutionGraph::decode(&invalid, &bound).is_err());
        }
    }
}
