"""llama-index-trust-gate -- LlamaIndex tools for Trust Gate post-quantum receipts.

Exposes two FunctionTool factories any LlamaIndex agent can pick up:

  mint_action_receipt_tool() -> FunctionTool
  verify_receipt_tool() -> FunctionTool

Usage:
    from llama_index.core.agent import ReActAgent
    from llama_index_trust_gate import mint_action_receipt_tool, verify_receipt_tool
    agent = ReActAgent.from_tools([mint_action_receipt_tool(), verify_receipt_tool()], llm=...)
"""
from llama_index_trust_gate.tool import mint_action_receipt_tool, verify_receipt_tool

__version__ = "0.1.0"
__all__ = ["mint_action_receipt_tool", "verify_receipt_tool", "__version__"]
