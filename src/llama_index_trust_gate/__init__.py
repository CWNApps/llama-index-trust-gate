"""llama-index-trust-gate -- LlamaIndex tools for Trust Gate post-quantum receipts.

Exposes five FunctionTool factories any LlamaIndex agent can pick up:

  mint_action_receipt_tool() -> FunctionTool   -- receipt for a consequential action
  verify_receipt_tool() -> FunctionTool        -- verify from the certificate alone
  gate_decision_tool() -> FunctionTool         -- two-phase PREVIEW -> COMMIT gate
  check_egress_tool() -> FunctionTool          -- classify data before it leaves
  run_exit_drill_tool() -> FunctionTool        -- vendor exit-readiness drill

Receipts are signed Ed25519 + ML-DSA-65 (FIPS 204); PQ-required verify defaults on.

Usage:
    from llama_index.core.agent import ReActAgent
    from llama_index_trust_gate import mint_action_receipt_tool, verify_receipt_tool
    agent = ReActAgent.from_tools([mint_action_receipt_tool(), verify_receipt_tool()], llm=...)
"""
from llama_index_trust_gate.tool import (
    check_egress_tool,
    gate_decision_tool,
    mint_action_receipt_tool,
    run_exit_drill_tool,
    verify_receipt_tool,
)

__version__ = "0.2.0"
__all__ = [
    "mint_action_receipt_tool",
    "verify_receipt_tool",
    "gate_decision_tool",
    "check_egress_tool",
    "run_exit_drill_tool",
    "__version__",
]
