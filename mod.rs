//! # Protocol Adapters
//!
//! This module contains the protocol-specific logic for quoting and interacting
//! with different DEX invariants (e.g., Uniswap V3, Algebra). Each submodule
//! represents a distinct adapter, ensuring that logic is not incorrectly shared
//! between protocols with different on-chain implementations.
//!
//! This aligns with Step 3 of the implementation plan, which mandates a
//! strict separation between the Uniswap V3 and Algebra paths.

pub mod algebra;
pub mod errors;
pub mod uniswap_v3;

// A trait could be defined here in the future to standardize adapter interfaces.
// pub trait ProtocolAdapter { ... }