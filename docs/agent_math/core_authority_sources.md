# Core Authority Sources

Validated on `2026-04-23`.

This document fixes the source-governance boundary for the agent mathematics program. Only the sources below may anchor the core theory.

## Core Set

| ID | Source | Status | Layer | Why It Stays |
| --- | --- | --- | --- | --- |
| S01 | [Attention Is All You Need](https://arxiv.org/abs/1706.03762) | foundational paper | LLM base | Defines the Transformer architecture and attention computation. |
| S02 | [Deep Learning: Foundations and Concepts](https://link.springer.com/book/10.1007/978-3-031-45468-4) | Springer 2024 | LLM base | Primary textbook for modern deep-learning notation and optimization language. |
| S03 | [Pattern Recognition and Machine Learning](https://link.springer.com/book/10.1007/978-0-387-45528-0) | Springer 2006 | probabilistic base | Primary reference for Bayesian modeling, latent variables, and approximate inference. |
| S04 | [Elements of Information Theory](https://www.wiley-vch.de/en/areas-interest/computing-computer-sciences/elements-of-information-theory-978-0-471-24195-9) | Wiley | information base | Entropy, KL divergence, mutual information, and value-of-information language. |
| S05 | [Scaling Laws for Neural Language Models](https://arxiv.org/abs/2001.08361) | foundational paper | training | Capacity, data, and compute scaling behavior. |
| S06 | [Training language models to follow instructions with human feedback](https://arxiv.org/abs/2203.02155) | foundational paper | alignment | Canonical RLHF formulation for post-training alignment. |
| S07 | [Direct Preference Optimization](https://arxiv.org/abs/2305.18290) | foundational paper | alignment | Preference optimization without an explicit online RL loop. |
| S08 | [A Survey on Efficient Large Language Model Training: From Data-centric Perspectives](https://aclanthology.org/2025.acl-long.1493/) | ACL 2025 | training | Latest core survey for training efficiency and post-training data regimes. |
| S09 | [Reliable and Responsible Foundation Models](https://openreview.net/forum?id=nLJZh4M6S5) | TMLR accepted, published 2025-10-05 | safety | Reliable and responsible model behavior under deployment constraints. |
| S10 | [A Survey on Training-free Alignment of Large Language Models](https://aclanthology.org/2025.findings-emnlp.238/) | EMNLP Findings 2025 | runtime alignment | Runtime alignment and decoding-time steering. |
| S11 | [The Landscape of Agentic Reinforcement Learning for LLMs: A Survey](https://openreview.net/forum?id=RY19y2RI1O) | TMLR accepted, published 2026-01-14 | agent math | Moves the discussion from single-shot generation toward partially observed decision processes. |
| S12 | [Towards Rationality in Language and Multimodal Agents: A Survey](https://aclanthology.org/2025.naacl-long.186/) | NAACL 2025 | agent math | Rationality, objectives, action quality, and tool-grounded behavior. |
| S13 | [LLMs as Planning Formalizers](https://aclanthology.org/2025.findings-acl.1291/) | ACL Findings 2025 | planning | Formal planning and structured decomposition. |
| S14 | [Large Language Model-Brained GUI Agents: A Survey](https://openreview.net/forum?id=xChvYjvXTp) | TMLR accepted, published 2025-06-12 | action | Large action spaces, execution loops, and environment interaction. |
| S15 | [A Survey on Large Language Model-Based Social Agents in Game-Theoretic Scenarios](https://openreview.net/forum?id=CsoSWpR5xC) | TMLR accepted, published 2025-05-09 | multi-agent | Strategic interaction, belief over other agents, and preference conflict. |
| S16 | [Towards a Design Guideline for RPA Evaluation](https://aclanthology.org/2025.findings-acl.938/) | ACL Findings 2025 | evaluation | Evaluation design, traceability, and behavioral criteria. |
| S17 | [Position: Trustworthy AI Agents Require the Integration of Large Language Models and Formal Methods](https://openreview.net/forum?id=wkisIZbntD) | ICML 2025 Position Paper | verification | Formal-method perspective for verifiable agents. |
| S18 | [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401) | foundational paper | retrieval | Canonical retrieval-augmented generation formulation. |
| S19 | [A Survey of RAG-Reasoning Systems in Large Language Models](https://aclanthology.org/2025.findings-emnlp.648/) | EMNLP Findings 2025 | retrieval | Latest authoritative survey on retrieval plus reasoning loops. |
| S20 | [Markov Decision Processes](https://www.wiley-vch.de/en/areas-interest/mathematics-statistics/markov-decision-processes-978-0-471-72782-8) | Wiley | decision theory | Canonical MDP reference for value, policy, and constrained decision logic. |
| S21 | [Planning and acting in partially observable stochastic domains](https://www.sciencedirect.com/science/article/pii/S000437029800023X) | Artificial Intelligence journal | decision theory | Canonical POMDP and belief-state reference. |
| S22 | [LAMBDA: A Large Model Based Data Agent](https://www.tandfonline.com/doi/abs/10.1080/01621459.2025.2510000) | JASA | data-agent domain | Formal reference point for data-agent workflow design. |
| S23 | [A Survey on Large Language Model-based Agents for Statistics and Data Science](https://www.tandfonline.com/doi/full/10.1080/00031305.2025.2561140) | The American Statistician, online 2025-10-16 | data-agent domain | Statistics and data-science agent framing. |
| S24 | [Large Language Model-based Data Science Agent: A Survey](https://openreview.net/forum?id=ZT5SJQN0CS) | TMLR accepted, published 2026-02-08 | data-agent domain | Latest accepted survey for data-science agent systems. |

## Auxiliary But Non-Core

| ID | Source | Status | Role |
| --- | --- | --- | --- |
| A01 | [A Mathematical Framework for Transformer Circuits](https://www.anthropic.com/research/a-mathematical-framework-for-transformer-circuits) | official research note | Useful for mechanistic intuition, but it cannot override the core papers and textbooks. |

## Exclusion Rules

The following sources are excluded from the core skeleton even if they are useful for horizon scanning:

- `under review` OpenReview, ARR, or TMLR entries
- workshop-only publications
- blogs, secondary explainers, and informal summaries
- external project prompts, variable names, repo structure, and UI copy
- unpublished survey drafts on memory, human-agent systems, or structured-data interfaces

## Explicitly Excluded Examples

| ID | Source | Why It Is Excluded |
| --- | --- | --- |
| X01 | `Rethinking Memory Mechanisms of Foundation Agents in the Second Half: A Survey` | under review |
| X02 | `Large Language Models as Interfaces to Structured Data: A Survey` | under review |
| X03 | `A Survey on Large Language Model based Human-Agent Systems` | not formally published in the validated core set |

## Usage Policy

- Every core concept in the whitepaper must cite at least one of `S01-S24`.
- Every "latest state" claim must rely on a 2025-2026 formally published or accepted source.
- Every foundational claim must prefer the canonical original paper or textbook even if a newer survey exists.
- Publication-status checks should be recorded in [source_status_log.md](./source_status_log.md).
