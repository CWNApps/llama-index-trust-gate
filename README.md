# llama-index-trust-gate

LlamaIndex tools for **Trust Gate** post-quantum, tamper-evident receipts on consequential agent actions.

Trust Gate receipts are signed Ed25519 + ML-DSA-65 (FIPS 204) by the hosted MCP server (no local signing key). Each receipt is verifiable offline from the certificate alone. The hosted server defaults to PQ-required verify mode; set TRUST_GATE_REQUIRE_PQ=false to allow Ed25519-only receipts.

## Install

```bash
pip install cwn-llama-index-trust-gate
```

## Usage

```python
from llama_index.core.agent import ReActAgent
from llama_index_trust_gate import mint_action_receipt_tool, verify_receipt_tool

agent = ReActAgent.from_tools(
    [mint_action_receipt_tool(), verify_receipt_tool()],
    llm=...,
)
```

## Tools

| Factory | Name | Purpose |
|---|---|---|
| `mint_action_receipt_tool()` | `trust_gate_mint_action_receipt` | Mint a post-quantum receipt for any consequential agent action. |
| `verify_receipt_tool()` | `trust_gate_verify_receipt` | Verify a Trust Gate receipt from the certificate alone (offline). |

## Configuration

```bash
export TRUST_GATE_URL="https://trust-gate-mcp.onrender.com"  # default; override for self-hosted
```

## Telemetry

One fire-and-forget `GET /x?via=llamaindex&kind=api` per tool call. No PII, no cookies, never blocks the tool.

## Related

* **langchain-trust-gate** -- same tools, LangChain shape
* **crewai-trust-gate** -- same tools, CrewAI shape
* **Trust Gate MCP** -- the hosted server: <https://trust-gate-mcp.onrender.com>

## License

Apache-2.0.
