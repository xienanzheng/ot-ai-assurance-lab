# Plant context and local retrieval

Qwen now has an opt-in retrieval path for a versioned, source-linked JSON knowledge pack covering the simulated water, grid and conceptual nuclear models. This augments the prompt; it does not fine-tune weights or establish improved control performance.

## Use it

In the Agent inspection lab, select **Plant knowledge → Plant records · local embeddings**, then run an evaluation-only decision. Expand **Retrieved plant knowledge and sources** in its evidence record. Modes are per-call and do not modify other sessions or scheduled workers.

For scheduled local decisions, set `PLANT_KNOWLEDGE_MODE=hybrid` in `.env` and recreate the supervisor service. `lexical` works without an embedding model; `off` retains baseline context. The default remains off pending evaluation.

Install the embedding model once while connected:

```sh
ollama pull embeddinggemma
KNOWLEDGE_EMBED_URL=http://127.0.0.1:11434 \
  python -m services.supervisor.app.plant_knowledge --prepare
```

It was installed on the development machine for this change. With the model cached and Ollama local, retrieval needs no Internet connection. `KNOWLEDGE_EMBED_URL` accepts loopback or Docker's host alias only. The hosted container never calls this local endpoint; requesting hybrid there explicitly falls back to keyword retrieval. Hosted Qwen inference itself remains a cloud service.

## What enters a decision

1. Current sensors, units, quality flags, equipment, setpoints and fixed limits remain directly supplied. Retrieval does not replace these inputs.
2. Exact domain/scenario/mode and available equipment/sensor filters limit eligible records.
3. Alarm text, abnormal sensor names and quality flags form a focused retrieval query. Full PLC/history dumps are excluded from embedding inputs. Numeric comparisons use code, not embedding similarity.
4. Hybrid ranking combines BM25 and vector ranks using reciprocal rank fusion. Exact abnormal sensor matches break relevance ties. At most two records within a 2,400-byte evidence budget are selected; only IDs, titles and record text enter the model prompt. A high similarity score is not a safety probability.
5. Audit evidence includes pack version/hash, selected records and source paths, state hash, query, embedding model digest, cache hits, retrieval duration and any fallback. Model-visible context excludes timing metadata.

Preparation allows 60 seconds per embedding request for cold startup. Decision retrieval allows 30 seconds by default (`KNOWLEDGE_EMBED_TIMEOUT`) before an explicit keyword fallback. Warm the cache before measuring latency.

Static document embeddings are cached in SQLite, keyed by content and embedding model digest. Live query embeddings are not persisted in that cache. Exact requests and queries still appear in the existing decision audit database. Pack or embedding failures yield empty or explicitly labelled keyword context; they cannot expand control authority. No public document ingestion endpoint is introduced.

The pack is `services/supervisor/app/plant_knowledge.json`. Update its version and review source references whenever simulator semantics change. Records use explicit sensor tags and conceptual equipment relationships; all content is simulator-specific and is not a real-facility procedure library.

## Learning from outcomes

Existing critical-event archives and versioned lesson review remain in place. A candidate lesson must have source events, an exact domain/scenario/model scope, operator approval and a future expiry before retrieval. Revocation removes it from subsequent prompts. Gate acceptance alone does not establish a useful lesson. `LESSON_MEMORY_ENABLED` remains a separate opt-in; comparison runs disable it to isolate the static-knowledge effect.

No automatic weight updates, reinforcement learning or promotion of model-written lessons occurs. Fine-tuning should follow a sufficiently large reviewed dataset and held-out evaluation.

## Reproduce comparisons

Use the project Python environment with supervisor requirements and plant simulator dependencies installed:

```sh
python scripts/compare_plant_retrieval.py --output /tmp/retrieval-frozen \
  --domains water grid nuclear --seeds 101 202 --modes off hybrid

python scripts/compare_plant_retrieval.py --output /tmp/retrieval-timeline \
  --timeline --minutes 40 --interval 10 --seeds 101 202 --modes off hybrid
```

The default decision model is `qwen3:4b`; override with `--model`. Runs use detached in-process simulators and a separate output audit database. They never submit commands to an existing lab or real equipment. Seeds reverse execution order to reduce systematic order effects; this does not eliminate cold-start or thermal bias.

Frozen comparisons retain full requests, actual model outputs, gate results, total latency and provider token counts when returned. They do not measure recovery. Water timelines apply only actual gate-approved values with bounded leases, feed recent samples and previous decisions into subsequent calls, and record later observations. Reports include unsafe-sample counts and an eight-minute sustained-recovery check from the existing timeline evaluator. Null recovery means recovery was not observed in the horizon. Correct escalation and unnecessary intervention require independently labelled cases and remain explicitly unmeasured.

Inspect failures and retrieval fallbacks before interpreting a comparison. Compare repeated held-out scenarios and seeds, not just gate acceptance. These are simulated exploratory measurements, not evidence of real-plant safety.

Embedding API reference: https://docs.ollama.com/api/embed


## September 23 retrieval improvements

Contextual document text now carries the plant domain, process relationship and sensor tags rather than embedding raw JSON metadata. EmbeddingGemma receives its documented query/document prefixes. BM25 preserves exact sensor tags and supports term-frequency/length normalization; reciprocal rank fusion avoids adding incompatible cosine and lexical score scales. Near-duplicate records are removed. Full source provenance stays in the audit rather than increasing every Qwen prompt.

A one-off `text-embedding-3-large` job embedded nine documents and 18 simulated evaluation questions (3,072 dimensions, 1,083 input tokens). It reads `OPENAI_API_KEY` from the root `.env.local`, which is Git-ignored and owner-readable only. No key is sent to the frontend or deployed.

```sh
python scripts/embed_plant_knowledge.py --output artifacts/retrieval-v2/openai-large.json
python scripts/evaluate_retrieval.py --openai artifacts/retrieval-v2/openai-large.json --output artifacts/retrieval-v2
```

The embedding script refuses to overwrite an existing output, avoiding accidental repeat charges. Cached OpenAI vectors can be reused for those exact documents/questions. New free-form queries still need embeddings from that same model: local EmbeddingGemma query vectors cannot search the OpenAI space. The production runtime therefore retains local retrieval; this one-off job is an evaluation artifact, not an ongoing cloud dependency.

On the 18 developer-authored simulated queries, legacy keyword ranking found the expected top result in 17/18 cases. BM25, local hybrid and OpenAI hybrid each scored 18/18. Both dense-only models scored 17/18. This small set does not establish general superiority, control accuracy or improved recovery. It supports using the cheaper local/BM25 path for this small corpus while expanding the evaluation set.

Sources used in the design:
- [Contextual retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
- [Reciprocal rank fusion](https://learn.microsoft.com/azure/search/hybrid-search-ranking)
- [EmbeddingGemma retrieval prefixes](https://ai.google.dev/gemma/docs/embeddinggemma/inference-embeddinggemma-with-sentence-transformers)
- [OpenAI embedding dimensions and API](https://developers.openai.com/api/docs/guides/embeddings)
