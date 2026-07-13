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


# --- sovereignty v0.2.0 tools ----------------------------------------------------

def _gate_decision(
    action: str,
    resource: str,
    context: Dict[str, Any],
    phase: str = "PREVIEW",
    preview_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Two-phase decision gate: PREVIEW evaluates risk, COMMIT mints a receipt.

    PREVIEW returns a risk assessment and preview_id without acting.
    COMMIT requires the preview_id, verifies inputs match, and mints a
    tamper-evident receipt. Stateless -- preview_id is deterministic.
    """
    _ping_telemetry()
    args: Dict[str, Any] = {
        "action": action, "resource": resource,
        "context": context, "phase": phase,
    }
    if preview_id is not None:
        args["preview_id"] = preview_id
    return _mcp_call("gate_decision", args)


def _check_egress(
    destination: str,
    data_sample: str,
    provider: str,
) -> Dict[str, Any]:
    """Classify outbound data sensitivity and gate egress.

    Scans data_sample for sensitivity markers (heuristic) and classifies as
    PUBLIC / INTERNAL / CONFIDENTIAL / RESTRICTED. Blocks RESTRICTED-class.
    Returns classification, retention info, and a tamper-evident receipt.
    """
    _ping_telemetry()
    return _mcp_call("check_egress", {
        "destination": destination, "data_sample": data_sample, "provider": provider,
    })


def _run_exit_drill() -> Dict[str, Any]:
    """Vendor exit readiness drill: local signing, local model, local data export.

    Informational -- no side effects. Returns step-by-step results and a
    tamper-evident receipt.
    """
    _ping_telemetry()
    return _mcp_call("run_exit_drill", {})


def gate_decision_tool() -> FunctionTool:
    """Build a LlamaIndex FunctionTool for the two-phase decision gate."""
    return FunctionTool.from_defaults(
        fn=_gate_decision,
        name="trust_gate_gate_decision",
        description=(
            "Two-phase decision gate. PREVIEW returns risk assessment + preview_id. "
            "COMMIT requires preview_id, verifies inputs, mints tamper-evident receipt."
        ),
    )


def check_egress_tool() -> FunctionTool:
    """Build a LlamaIndex FunctionTool for egress classification."""
    return FunctionTool.from_defaults(
        fn=_check_egress,
        name="trust_gate_check_egress",
        description=(
            "Egress classification. Scans data for sensitivity markers, classifies as "
            "PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED. Blocks RESTRICTED. Returns receipt."
        ),
    )


def run_exit_drill_tool() -> FunctionTool:
    """Build a LlamaIndex FunctionTool for vendor exit readiness."""
    return FunctionTool.from_defaults(
        fn=_run_exit_drill,
        name="trust_gate_run_exit_drill",
        description=(
            "Vendor exit readiness drill. Checks local signing, model access, data export. "
            "Returns results + tamper-evident receipt. No side effects."
        ),
    )
