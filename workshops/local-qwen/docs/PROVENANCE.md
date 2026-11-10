# Provenance and interpretation

V2 was implemented as an independent local integration bench on 24 October 2026. It does not import V1 source, use its database or publish changes to its hosted deployment.

## Implemented, simulated and proposed

| Item | Status |
|---|---|
| Typed snapshots/proposals, package hashes, range/timing gate, durable receipts | Implemented |
| OPC UA client/server, FastAPI receiver, PostgreSQL, React UI | Real local software integration |
| Water and cooling response | New simplified first-order simulations; no physical calibration |
| Fixture decision provider | Deterministic test policy; not AI inference |
| Local Qwen/Gemma calls | Real Ollama calls when available; trial records retained separately |
| Qwen adaptation | No training or fine-tuned adapter selection in this V2 build |
| SOPs/relationships | Authored bench context; not site-approved operating procedures |
| Independent PLC runtime / hardware / external site | Not connected or qualified |
| Generic vendor tag mapping / physical writes | Not implemented |
| Cloud deployment | Not performed |

The first-order water model does not calculate chemistry, microbial risk, hydraulic pressure or regulatory compliance. The cooling model does not model a refrigerant circuit or equipment damage. These packages test integration semantics and delayed observation.

## Dependencies and useful next-stage projects

- [asyncua](https://github.com/FreeOpcUa/opcua-asyncio): OPC UA implementation used here (LGPL-3.0).
- [OpenPLC runtime](https://github.com/Autonomy-Logic/openplc-runtime): candidate independent software PLC for a later bench; not used as the current controller.
- [Eclipse Milo](https://github.com/eclipse-milo/milo): candidate independent OPC UA peer for interoperability tests; not included.
- [Fledge](https://github.com/fledge-iot/fledge): possible future industrial acquisition layer; not installed.
- [WNTR](https://github.com/USEPA/WNTR): potential later hydraulic model; not the source of these process equations.
- [NIST SP 800-82 Rev. 3](https://csrc.nist.gov/pubs/sp/800/82/r3/final): OT integration reference; this bench does not establish compliance.

Package files and JSON contracts are versioned. `web/package-lock.json` locks frontend transitive dependencies. Python direct dependencies are pinned in `pyproject.toml`; resolved runtime versions and image IDs should accompany each qualification export. Base image tags and Python transitive dependencies are not yet a fully reproducible supply-chain lock.

## Claims this evidence does not support

A successful receipt proves the local simulated receiver accepted that identified request. A completed outcome means the sampled variable met the package's band and dwell rule. Neither proves that the model uniquely caused recovery, that its root-cause diagnosis is correct, or that the integration is suitable for an operating plant.

Audit rationales and model-emitted text are observable outputs, not verified access to internal reasoning. No certification, formal guarantee, physical plant validation or general model-quality improvement is claimed.
