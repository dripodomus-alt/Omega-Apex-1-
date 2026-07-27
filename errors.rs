//! # Protocol Errors
//!
//! Defines custom errors for failures that can occur within a protocol adapter,
//! such as a failed on-chain quote.

#[derive(Debug, thiserror::Error)]
pub enum ProtocolError {
    #[error("On-chain quote simulation failed: {0}")]
    QuoteFailed(String),
}