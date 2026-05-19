# agentmem-bench

A reproducible benchmark for **multi-agent memory systems** — the gap LoCoMo, LongMemEval, and ConvoMem don't cover.

This repo is the methodology + harness + datasets, not a product. Read [`DESIGN.md`](./DESIGN.md) before running anything.

## Why another benchmark

LoCoMo (Maharana et al., ACL 2024) and LongMemEval (ICLR 2025) measure **single-agent long-term memory** — does the model recall what was said earlier? Useful, but Letta has publicly argued these measure retrieval, not agent memory ([Letta blog, 2025](https://www.letta.com/blog/long-conversation-locomo)). And **no existing benchmark stresses multi-agent coordination on memory**: contradictory writes, scope leakage, CRDT convergence, policy enforcement.

`agentmem-bench` fills that gap. We test scenarios with **multiple agents writing and reading shared memory**, and score whether the system:

1. Surfaces or auto-resolves contradictions according to the user's policy
2. Enforces visibility scopes (private / team / global)
3. Converges to a consistent state under concurrent writes (CRDT property)
4. Returns the right answer at the right time (temporal validity)
5. Doesn't leak across workflows / orgs

We run the same scenarios against every shipped memory system (Mem0, Zep, Cognee, Supermemory, LangMem, raw pgvector, AgentMem) on the same hardware with the same LLM, and publish reproducible numbers.

## Status

**Design phase.** See [`DESIGN.md`](./DESIGN.md). No harness code yet. Implementation lands in a follow-up.

## License

[Apache-2.0](./LICENSE) (TBD)
