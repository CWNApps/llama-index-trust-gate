"""Tests for llama-index-trust-gate."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

import llama_index_trust_gate.tool as tool_mod
from llama_index_trust_gate import mint_action_receipt_tool, verify_receipt_tool


def _mcp_response(structured: dict):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={
        "jsonrpc": "2.0", "id": 1,
        "result": {"structuredContent": structured},
    })
    return resp


def test_mcp_call_envelope():
    captured = {}
    def fake_post(self, url, json=None, **kw):
        captured["json"] = json
        return _mcp_response({"ok": True})
    with patch("httpx.Client.post", new=fake_post), patch("httpx.Client.get", new=lambda *a, **kw: MagicMock()):
        tool_mod._mcp_call("mint_action_receipt", {"agent_id": "a", "operation": "o", "target": "t"})
    assert captured["json"]["method"] == "tools/call"
    assert captured["json"]["params"]["name"] == "mint_action_receipt"


def test_telemetry_via_llamaindex():
    pings = []
    def fake_get(self, url, params=None, **kw):
        pings.append(params)
        return MagicMock()
    with patch("httpx.Client.post", return_value=_mcp_response({"ok": True})), \
         patch("httpx.Client.get", new=fake_get):
        tool_mod._mint_action_receipt(agent_id="a", operation="o", target="t")
    assert pings[0]["via"] == "llamaindex"


def test_telemetry_failure_never_breaks_tool():
    def fake_get(self, *a, **kw):
        import httpx
        raise httpx.ConnectError("simulated")
    with patch("httpx.Client.post", return_value=_mcp_response({"ok": True})), \
         patch("httpx.Client.get", new=fake_get):
        out = tool_mod._mint_action_receipt(agent_id="a", operation="o", target="t")
    assert out["ok"] is True


def test_verify_passes_require_pq():
    captured = {}
    def fake_post(self, url, json=None, **kw):
        captured["args"] = json["params"]["arguments"]
        return _mcp_response({"ok": True})
    with patch("httpx.Client.post", new=fake_post), patch("httpx.Client.get", return_value=MagicMock()):
        tool_mod._verify_receipt(receipt={"atom_id": "x"}, require_pq=False)
    assert captured["args"]["require_pq"] is False


def test_verify_default_omits_require_pq():
    captured = {}
    def fake_post(self, url, json=None, **kw):
        captured["args"] = json["params"]["arguments"]
        return _mcp_response({"ok": True})
    with patch("httpx.Client.post", new=fake_post), patch("httpx.Client.get", return_value=MagicMock()):
        tool_mod._verify_receipt(receipt={"atom_id": "x"})
    assert "require_pq" not in captured["args"]


def test_tool_factories_return_function_tools():
    t1 = mint_action_receipt_tool()
    t2 = verify_receipt_tool()
    assert t1.metadata.name == "trust_gate_mint_action_receipt"
    assert t2.metadata.name == "trust_gate_verify_receipt"
    assert "post-quantum" in t1.metadata.description.lower()
    assert "offline" in t2.metadata.description.lower()


def test_mcp_call_raises_on_error():
    err = MagicMock()
    err.raise_for_status = MagicMock()
    err.json = MagicMock(return_value={"jsonrpc": "2.0", "error": {"message": "nope"}})
    with patch("httpx.Client.post", return_value=err), patch("httpx.Client.get", return_value=MagicMock()):
        with pytest.raises(RuntimeError, match="Trust Gate MCP error"):
            tool_mod._mcp_call("verify_receipt", {"receipt": {}})
