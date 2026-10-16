use agent_terminal_ui_native::run_inspector::*;
use ratatui::{Terminal, backend::TestBackend};
use std::time::{Duration, Instant};

fn projection() -> RunProjection {
    RunProjection {
        run_id: "run-1".into(),
        peak_context_tokens: Some(0),
        context_budget_tokens: None,
        cost_usd: Some(0.0),
        termination_reason: Some("context_overflow".into()),
        config: AppliedConfig {
            reference: Some("decision-1".into()),
            context_policy: Some("recorded-policy".into()),
            plan_scaffold: None,
            action_space: None,
        },
        current_plan: Some(PlanSnapshot {
            run_id: "run-1".into(),
            revision: "opaque-A".into(),
            observed_at: "producer-time".into(),
            items: vec![
                PlanItem {
                    text: "first-private-item".into(),
                    status: PlanStatus::Done,
                },
                PlanItem {
                    text: "second-item".into(),
                    status: PlanStatus::InProgress,
                },
                PlanItem {
                    text: "third-item".into(),
                    status: PlanStatus::Pending,
                },
            ],
        }),
    }
}
struct FixtureValidator;
impl PlanValidator for FixtureValidator {
    fn validate(
        &self,
        plan: &PlanSnapshot,
        previous: Option<&str>,
        now: Instant,
    ) -> Result<Instant, PlanRefusal> {
        // Fixture-only ordering; production must use the future AU contract.
        if previous == Some("opaque-A") && plan.revision == "older-fixture" {
            return Err(PlanRefusal::Regressing);
        }
        if plan.revision == "expired-fixture" {
            return Err(PlanRefusal::Expired);
        }
        Ok(now + Duration::from_secs(5))
    }
}
fn ready(now: Instant) -> RunInspector {
    let mut state = RunInspector::new("run-1".into());
    state
        .accept(Ok(projection()), Some(&FixtureValidator), now)
        .unwrap();
    state
}

// spec: TUI-RUNTIME-R010.7
#[test]
fn renders_recorded_configuration_and_zero_separately_from_unavailable() {
    let now = Instant::now();
    let mut state = ready(now);
    let mut terminal = Terminal::new(TestBackend::new(100, 25)).unwrap();
    terminal
        .draw(|frame| state.render(frame, frame.area(), now))
        .unwrap();
    let screen: String = terminal
        .backend()
        .buffer()
        .content
        .iter()
        .map(|cell| cell.symbol())
        .collect();
    for text in [
        "Peak context tokens: 0",
        "Context budget tokens: unavailable",
        "Per-run cost (USD): 0",
        "decision-1",
        "recorded-policy",
        "Plan scaffold: unavailable",
    ] {
        assert!(screen.contains(text), "{text}");
    }
    let mut run = projection();
    run.cost_usd = None;
    run.config.reference = None;
    state.accept(Ok(run), None, now).unwrap();
    let text = state.text(now);
    assert!(text.contains("Per-run cost (USD): unavailable"));
    assert!(!text.contains("recorded-policy"));
}

// spec: TUI-RUNTIME-R010.7
#[test]
fn invalid_cost_never_displays_as_measurement() {
    for cost in [f64::NAN, f64::INFINITY, -1.0] {
        let now = Instant::now();
        let mut state = ready(now);
        let mut run = projection();
        run.cost_usd = Some(cost);
        state.accept(Ok(run), None, now).unwrap();
        assert!(state.text(now).contains("Per-run cost (USD): unavailable"));
    }
}

// spec: TUI-RUNTIME-R010.7
#[test]
fn plan_is_ordered_and_empty_is_distinct_from_unavailable() {
    let now = Instant::now();
    let mut state = ready(now);
    let text = state.text(now);
    assert!(text.contains("Current plan revision: opaque-A"));
    assert!(text.contains("Observed at: producer-time"));
    assert!(text.find("[done] first").unwrap() < text.find("[in_progress] second").unwrap());
    assert!(text.contains("[pending] third"));
    let mut run = projection();
    run.current_plan.as_mut().unwrap().items.clear();
    state
        .accept(Ok(run.clone()), Some(&FixtureValidator), now)
        .unwrap();
    assert!(state.text(now).contains("available (empty)"));
    state.accept(Ok(run), None, now).unwrap();
    assert!(state.text(now).contains("Current plan: unavailable"));
}

// spec: TUI-RUNTIME-R010.7
#[test]
fn wrong_run_stale_regressing_and_malformed_plans_disclose_no_items() {
    for kind in ["wrong-run", "expired-fixture", "older-fixture", "malformed"] {
        let now = Instant::now();
        let mut state = ready(now);
        let mut run = projection();
        let plan = run.current_plan.as_mut().unwrap();
        match kind {
            "wrong-run" => plan.run_id = "other-run".into(),
            "malformed" => plan.observed_at.clear(),
            _ => plan.revision = kind.into(),
        }
        state.accept(Ok(run), Some(&FixtureValidator), now).unwrap();
        let text = state.text(now);
        assert!(text.contains("Current plan: unavailable"));
        assert!(!text.contains("first-private-item"));
        assert!(text.contains("Per-run cost (USD): 0"));
    }
    let now = Instant::now();
    let mut state = ready(now);
    let text = state.text(now + Duration::from_secs(5));
    assert!(!text.contains("first-private-item"));
    assert!(!text.contains("opaque-A"));
}

// spec: TUI-RUNTIME-R010.7
#[test]
fn terminal_reasons_remain_distinct_and_unknown_is_unavailable() {
    let labels: std::collections::HashSet<_> = [
        "final_answer",
        "context_overflow",
        "stuck",
        "step_budget",
        "error",
    ]
    .map(|r| terminal_reason(Some(r)))
    .into_iter()
    .collect();
    assert_eq!(labels.len(), 5);
    assert_eq!(terminal_reason(None), "unavailable");
    assert_eq!(terminal_reason(Some("future-reason")), "unavailable");
}

// spec: TUI-RUNTIME-R010.7
#[test]
fn refusals_and_run_switch_clear_all_protected_display_values() {
    for refusal in [
        ReadRefusal::Unavailable,
        ReadRefusal::Denied,
        ReadRefusal::Timeout,
    ] {
        let now = Instant::now();
        let mut state = ready(now);
        assert_eq!(state.accept(Err(refusal.clone()), None, now), Err(refusal));
        assert_eq!(state.text(now), "Run: run-1\nRun inspector unavailable");
        let mut stale = projection();
        stale.current_plan.as_mut().unwrap().revision = "older-fixture".into();
        state
            .accept(Ok(stale), Some(&FixtureValidator), now)
            .unwrap();
        assert!(!state.text(now).contains("first-private-item"));
    }
    let now = Instant::now();
    let mut state = ready(now);
    state.select_run("run-2".into());
    assert_eq!(
        state.accept(Ok(projection()), Some(&FixtureValidator), now),
        Err(ReadRefusal::WrongRun)
    );
    assert_eq!(state.text(now), "Run: run-2\nRun inspector unavailable");
}
