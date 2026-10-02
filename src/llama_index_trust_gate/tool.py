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
    """Mint a signed receipt (Ed25519, plus ML-DSA-65 when the server has a post-quantum backend) for a consequential agent action.

    Returns the receipt dict; its integrity can be checked offline. The receipt carries a
    kid; compare it with the kid you trust (verify with expected_kid) to know which key signed it.
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
    expected_kid: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify a Trust Gate receipt from the receipt itself (no DB, no network).

    require_pq:
      None  -- obey TRUST_GATE_REQUIRE_PQ env on the server (default true)
      True  -- fail unless a post-quantum signature verifies
      False -- Ed25519-only verification is allowed (legacy receipts)
    expected_kid:
      kid of the signer you trust; when set, the receipt must be signed by that key and
      the result reports signer_pinned
    """
    _ping_telemetry()
    args: Dict[str, Any] = {"receipt": receipt}
    if require_pq is not None:
        args["require_pq"] = require_pq
    if expected_kid is not None:
        args["expected_kid"] = expected_kid
    return _mcp_call("verify_receipt", args)


# --- tool factories (the public API) --------------------------------------------------
def mint_action_receipt_tool() -> FunctionTool:
    """Build a LlamaIndex FunctionTool that mints a Trust Gate action receipt."""
    return FunctionTool.from_defaults(
        fn=_mint_action_receipt,
        name="trust_gate_mint_action_receipt",
        description=(
            "Mint a signed receipt (Ed25519, plus ML-DSA-65 when the server has a post-quantum backend) for a consequential agent action. Its "
            "integrity can be checked offline; to know which key signed it, verify it with "
            "expected_kid. A receipt is evidence of what was signed, not proof that the action "
            "was safe or met any requirement."
        ),
    )


def verify_receipt_tool() -> FunctionTool:
    """Build a LlamaIndex FunctionTool that verifies a Trust Gate receipt."""
    return FunctionTool.from_defaults(
        fn=_verify_receipt,
        name="trust_gate_verify_receipt",
        description=(
            "Verify a Trust Gate receipt from the receipt itself (offline). Returns ok plus the "
            "values it checked and signer_pinned. Pass expected_kid, the kid of the server you "
            "trust, to pin the signer: without it anyone's receipt can verify. With require_pq on "
            "(the server default) it fails unless a post-quantum signature verifies."
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
    """Two-phase decision gate: PREVIEW returns a verdict, COMMIT signs a receipt and returns a permit.

    The verdict (ALLOW, DENY or ESCALATE) comes from the server's read-only allowlist over
    the action name and resource; GRANTED exists only for ALLOW. It does not observe or block
    anything. Needs Trust Gate MCP server 0.3.0 or later.
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
    """Check outbound data for sensitivity markers.

    Scans data_sample for a finite list of markers (heuristic) and classifies it
    NO_MARKERS_FOUND / INTERNAL / CONFIDENTIAL / RESTRICTED. It flags and cannot block.
    Returns the classification, retention info and a signed receipt.
    """
    _ping_telemetry()
    return _mcp_call("check_egress", {
        "destination": destination, "data_sample": data_sample, "provider": provider,
    })


def _run_exit_drill() -> Dict[str, Any]:
    """Vendor exit readiness drill: local signing key and local model endpoint.

    Informational. Returns step-by-step results and a signed receipt; signing creates the
    signing key on first use.
    """
    _ping_telemetry()
    return _mcp_call("run_exit_drill", {})


def gate_decision_tool() -> FunctionTool:
    """Build a LlamaIndex FunctionTool for the two-phase decision gate."""
    return FunctionTool.from_defaults(
        fn=_gate_decision,
        name="trust_gate_gate_decision",
        description=(
            "Two-phase decision gate (needs Trust Gate MCP server 0.3.0 or later). PREVIEW "
            "returns a verdict (ALLOW, DENY or ESCALATE) and a preview_id without acting. COMMIT "
            "evaluates the same inputs again, signs a receipt and returns a permit: GRANTED only "
            "for ALLOW, DENIED for DENY, WITHHELD_PENDING_HUMAN for ESCALATE. It judges the "
            "action name and resource against a read-only allowlist and does not observe or block "
            "anything. Treat a GRANTED permit from a server older than 0.3.0 as not evidence."
        ),
    )


def check_egress_tool() -> FunctionTool:
    """Build a LlamaIndex FunctionTool for egress classification."""
    return FunctionTool.from_defaults(
        fn=_check_egress,
        name="trust_gate_check_egress",
        description=(
            "Egress marker check. Scans data for sensitivity markers and classifies it "
            "NO_MARKERS_FOUND, INTERNAL, CONFIDENTIAL or RESTRICTED. It flags and cannot block: "
            "act on a RESTRICTED result yourself. NO_MARKERS_FOUND is not clearance to send."
        ),
    )


def run_exit_drill_tool() -> FunctionTool:
    """Build a LlamaIndex FunctionTool for vendor exit readiness."""
    return FunctionTool.from_defaults(
        fn=_run_exit_drill,
        name="trust_gate_run_exit_drill",
        description=(
            "Vendor exit readiness drill. Checks that the local signing key works (and names the "
            "post-quantum backend) and whether a local model endpoint is configured (it is not "
            "contacted), and signs a receipt (which creates the signing key on first use)."
        ),
    )
