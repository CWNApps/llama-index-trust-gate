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
    assert "ML-DSA-65" in t1.metadata.description
    assert "offline" in t2.metadata.description.lower()


def test_mcp_call_raises_on_error():
    err = MagicMock()
    err.raise_for_status = MagicMock()
    err.json = MagicMock(return_value={"jsonrpc": "2.0", "error": {"message": "nope"}})
    with patch("httpx.Client.post", return_value=err), patch("httpx.Client.get", return_value=MagicMock()):
        with pytest.raises(RuntimeError, match="Trust Gate MCP error"):
            tool_mod._mcp_call("verify_receipt", {"receipt": {}})


# ---- 0.3.0: pinning the signer, and no claim the server's 0.3.0 documentation withdrew ------------
def test_verify_passes_expected_kid_through():
    captured = {}
    def fake_post(self, url, json=None, **kw):
        captured["args"] = json["params"]["arguments"]
        return _mcp_response({"ok": True, "signer_pinned": True})
    with patch("httpx.Client.post", new=fake_post), patch("httpx.Client.get", return_value=MagicMock()):
        tool_mod._verify_receipt(receipt={"atom_id": "x"}, expected_kid="0123456789abcdef0123456789abcdef")
    assert captured["args"]["expected_kid"] == "0123456789abcdef0123456789abcdef"


def test_verify_default_omits_expected_kid():
    captured = {}
    def fake_post(self, url, json=None, **kw):
        captured["args"] = json["params"]["arguments"]
        return _mcp_response({"ok": True})
    with patch("httpx.Client.post", new=fake_post), patch("httpx.Client.get", return_value=MagicMock()):
        tool_mod._verify_receipt(receipt={"atom_id": "x"})
    assert "expected_kid" not in captured["args"]


WITHDRAWN = ("certificate alone", "same notary", "same-notary", "execution permit", "Blocks RESTRICTED",
             "blocks RESTRICTED", "no side effects", "No side effects", "SLH-DSA", "defeats", "defends against",
             "data export", "who signed")


def _all_descriptions():
    from llama_index_trust_gate.tool import (check_egress_tool, gate_decision_tool, mint_action_receipt_tool,
                                             run_exit_drill_tool, verify_receipt_tool)
    return {f.__name__: f().metadata.description for f in (mint_action_receipt_tool, verify_receipt_tool,
                                                           gate_decision_tool, check_egress_tool, run_exit_drill_tool)}


def test_no_description_makes_a_claim_the_server_withdrew():
    for name, text in _all_descriptions().items():
        for phrase in WITHDRAWN:
            assert phrase not in text, (name, phrase)


def test_descriptions_state_what_the_server_does_and_does_not_do():
    d = _all_descriptions()
    assert "expected_kid" in d["verify_receipt_tool"]
    assert "ALLOW" in d["gate_decision_tool"] and "0.3.0" in d["gate_decision_tool"]
    assert "does not observe or block" in d["gate_decision_tool"]
    assert "cannot block" in d["check_egress_tool"] and "NO_MARKERS_FOUND" in d["check_egress_tool"]
    assert "signs a receipt" in d["run_exit_drill_tool"] and "local signing key" in d["run_exit_drill_tool"]
    assert "not contacted" in d["run_exit_drill_tool"]


def test_version_is_030_everywhere():
    import pathlib, re
    import llama_index_trust_gate as pkg
    toml = (pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert pkg.__version__ == "0.3.0"
    assert re.search(r'^version = "0.3.0"', toml, re.M)
