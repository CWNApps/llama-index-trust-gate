"""llama-index-trust-gate -- LlamaIndex tools for Trust Gate signed receipts.

Exposes five FunctionTool factories any LlamaIndex agent can pick up:

  mint_action_receipt_tool() -> FunctionTool   -- receipt for a consequential action
  verify_receipt_tool() -> FunctionTool        -- verify; pass expected_kid to pin the signer
  gate_decision_tool() -> FunctionTool         -- two-phase PREVIEW -> COMMIT gate
  check_egress_tool() -> FunctionTool          -- flag sensitive data before it leaves
  run_exit_drill_tool() -> FunctionTool        -- vendor exit-readiness drill

Receipts are signed with Ed25519, plus ML-DSA-65 when the server has a post-quantum backend; PQ-required verify defaults on at the server.

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

__version__ = "0.3.0"
__all__ = [
    "mint_action_receipt_tool",
    "verify_receipt_tool",
    "gate_decision_tool",
    "check_egress_tool",
    "run_exit_drill_tool",
    "__version__",
]
