//! C1 × C2 cycle event vocabulary (aligned with Python cycle_logger).
//! Python remains the durable DB/JSONL writer; Rust shares event names for engine logs.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum CycleType {
    Discovery,
    C1,
    C2,
    Liquidation,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum CycleEventType {
    Discovered,
    PriceEdgeValidated,
    SizeSelected,
    ProfitValidated,
    SimStarted,
    SimPassed,
    SimFailed,
    PayloadBuilt,
    SubmittedPrivate,
    SubmittedPublic,
    Confirmed,
    Reverted,
    Settled,
    C2WindowOpened,
    PostC1StateReloaded,
    C2MirrorEvaluated,
    C2ReverseEvaluated,
    C2NoopSelected,
    C2Expired,
    Archived,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CycleEvent {
    pub event_id: String,
    pub opportunity_id: String,
    pub cycle_id: String,
    pub cycle_type: CycleType,
    pub event_type: CycleEventType,
    pub event_status: String,
    pub block_number: Option<u64>,
    pub tx_hash: Option<String>,
    pub state_hash: Option<String>,
    pub route_hash: Option<String>,
    pub config_hash: Option<String>,
    pub message: String,
    pub created_at_ms: u64,
}

impl CycleEvent {
    pub fn to_json_line(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string(self)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cycle_event_serializes() {
        let ev = CycleEvent {
            event_id: "ev_1".into(),
            opportunity_id: "opp_1".into(),
            cycle_id: "c1_1".into(),
            cycle_type: CycleType::C1,
            event_type: CycleEventType::Settled,
            event_status: "OK".into(),
            block_number: Some(1),
            tx_hash: Some("0xabc".into()),
            state_hash: None,
            route_hash: None,
            config_hash: None,
            message: "C1 settled".into(),
            created_at_ms: 0,
        };
        let line = ev.to_json_line().expect("json");
        assert!(line.contains("SETTLED") || line.contains("Settled") || line.contains("settled"));
    }
}
