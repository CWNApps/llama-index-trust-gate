"""LlamaIndex tool factories around the hosted Trust Gate MCP server.

LlamaIndex tools are constructed via `FunctionTool.from_defaults(fn=...)` -- so we
expose Python functions that any agent can call. Same transport layer as the LangChain
and CrewAI adapters: one JSON-RPC POST to /mcp + one fire-and-forget telemetry ping to
/x?via=llamaindex. No PII, no cookies.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

try:
    from llama_index.core.tools import FunctionTool
except ImportError as e:
    raise ImportError(
        "llama-index-trust-gate requires llama-index-core. "
        "Install with: pip install llama-index-core (or "
        "`pip install llama-index-trust-gate[llama-index]`)."
    ) from e


TRUST_GATE_URL = os.environ.get("TRUST_GATE_URL", "https://trust-gate-mcp.onrender.com")
_VIA = "llamaindex"


def _mcp_call(method: str, arguments: Dict[str, Any], *, timeout: float = 30.0) -> Dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": method, "arguments": arguments},
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(
            f"{TRUST_GATE_URL}/mcp",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-03-26",
            },
        )
        r.raise_for_status()
        body = r.json()
    if "error" in body:
        raise RuntimeError(f"Trust Gate MCP error: {body['error']}")
    result = body.get("result", {})
    if isinstance(result, dict):
        if "structuredContent" in result:
            return result["structuredContent"]
        if "content" in result and result["content"]:
            try:
                import json
                return json.loads(result["content"][0]["text"])
            except (KeyError, ValueError, IndexError):
                return {"raw": result["content"]}
    return result if isinstance(result, dict) else {"raw": result}


def _ping_telemetry(kind: str = "api") -> None:
    try:
        with httpx.Client(timeout=2.0) as client:
            client.get(f"{TRUST_GATE_URL}/x", params={"via": _VIA, "kind": kind})
    except Exception:  # noqa: BLE001 -- telemetry is best-effort; ANY failure must be swallowed
        pass


# --- tool callables -------------------------------------------------------------------
def _mint_action_receipt(
    agent_id: str,
    operation: str,
    target: str,
    policy: str = "agent action evidence",
    inputs: Optional[str] = None,
    decision: str = "ACTION_GOVERNED",
) -> Dict[str, Any]:
    """Mint a post-quantum, tamper-evident receipt for a consequential agent action.

    Returns the receipt dict (verifiable offline from the certificate alone).
    The receipt is signed Ed25519 + ML-DSA-65 and carries a 128-bit kid for
    offline same-notary identification across receipts.
    """
    _ping_telemetry()
    args: Dict[str, Any] = {
        "agent_id": agent_id,
        "operation": operation,
        "target": target,
        "policy": policy,
        "decision": decision,
    }
    if inputs is not None:
        args["inputs"] = inputs
    return _mcp_call("mint_action_receipt", args)


def _verify_receipt(
    receipt: Dict[str, Any],
    require_pq: Optional[bool] = None,
) -> Dict[str, Any]:
    """Verify a Trust Gate receipt from the certificate alone (no DB, no network).

    require_pq:
      None  -- obey TRUST_GATE_REQUIRE_PQ env on the server (default true)
      True  -- fail unless at least one PQ leg verifies (defeats Ed25519-only downgrade)
      False -- Ed25519-only verification is allowed (legacy receipts)
    """
    _ping_telemetry()
    args: Dict[str, Any] = {"receipt": receipt}
    if require_pq is not None:
        args["require_pq"] = require_pq
    return _mcp_call("verify_receipt", args)


# --- tool factories (the public API) --------------------------------------------------
def mint_action_receipt_tool() -> FunctionTool:
    """Build a LlamaIndex FunctionTool that mints a Trust Gate action receipt."""
    return FunctionTool.from_defaults(
        fn=_mint_action_receipt,
        name="trust_gate_mint_action_receipt",
        description=(
            "Mint a post-quantum, tamper-evident receipt for a consequential agent action. "
            "Returns a receipt verifiable offline from the certificate alone. "
            "Signed Ed25519 + ML-DSA-65 (FIPS 204)."
        ),
    )


def verify_receipt_tool() -> FunctionTool:
    """Build a LlamaIndex FunctionTool that verifies a Trust Gate receipt."""
    return FunctionTool.from_defaults(
        fn=_verify_receipt,
        name="trust_gate_verify_receipt",
        description=(
            "Verify a Trust Gate receipt from the certificate alone (offline). "
            "Defaults to PQ-required mode -- defends against Ed25519-only downgrade "
            "by requiring at least one verified PQ leg."
        ),
    )
