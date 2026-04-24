# Source Status Log

This document records publication-status checks for the core authority set. It is a verification log, not a theory document.

Checked on `2026-04-24`.

## Verified Items

| ID | Source | Verified Status |
| --- | --- | --- |
| S01 | Attention Is All You Need | NeurIPS 2017 foundational paper / arXiv record. |
| S02 | Deep Learning: Foundations and Concepts | Springer textbook, copyright `2024`. |
| S03 | Pattern Recognition and Machine Learning | Springer textbook, copyright `2006`. |
| S04 | Elements of Information Theory | Wiley textbook reference. |
| S05 | Scaling Laws for Neural Language Models | Foundational arXiv paper, `2020`. |
| S06 | Training language models to follow instructions with human feedback | Foundational RLHF paper, arXiv `2022`. |
| S07 | Direct Preference Optimization | Foundational DPO paper, arXiv `2023`. |
| S08 | A Survey on Efficient Large Language Model Training: From Data-centric Perspectives | ACL Anthology record shows ACL 2025, DOI `10.18653/v1/2025.acl-long.1493`. |
| S09 | Reliable and Responsible Foundation Models | OpenReview/TMLR accepted record; used only for reliability and governance framing. |
| S10 | A Survey on Training-free Alignment of Large Language Models | ACL Anthology record shows Findings of EMNLP 2025, DOI `10.18653/v1/2025.findings-emnlp.238`. |
| S11 | The Landscape of Agentic Reinforcement Learning for LLMs: A Survey | OpenReview page shows TMLR publication on `2026-01-14`. |
| S12 | Towards Rationality in Language and Multimodal Agents: A Survey | ACL Anthology record shows NAACL 2025, DOI `10.18653/v1/2025.naacl-long.186`. |
| S13 | LLMs as Planning Formalizers | ACL Anthology record shows Findings of ACL 2025, DOI `10.18653/v1/2025.findings-acl.1291`. |
| S14 | Large Language Model-Brained GUI Agents: A Survey | OpenReview/TMLR accepted record; used for large action-space framing. |
| S15 | A Survey on Large Language Model-Based Social Agents in Game-Theoretic Scenarios | OpenReview/TMLR accepted record; used for multi-actor uncertainty framing. |
| S16 | Towards a Design Guideline for RPA Evaluation | ACL Anthology record shows Findings of ACL 2025, DOI `10.18653/v1/2025.findings-acl.938`. |
| S17 | Trustworthy AI Agents Require the Integration of Large Language Models and Formal Methods | ICML 2025 position-paper record; used for formal-method governance framing. |
| S18 | Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks | Foundational RAG paper, arXiv `2020`. |
| S19 | A Survey of RAG-Reasoning Systems in Large Language Models | ACL Anthology record shows Findings of EMNLP 2025, DOI `10.18653/v1/2025.findings-emnlp.648`. |
| S20 | Markov Decision Processes | Wiley decision-theory textbook reference. |
| S21 | Planning and acting in partially observable stochastic domains | Artificial Intelligence journal POMDP reference. |
| S22 | LAMBDA: A Large Model Based Data Agent | Taylor & Francis page shows accepted `2025-05-16`, published online `2025-07-17`. |
| S23 | A Survey on Large Language Model-based Agents for Statistics and Data Science | The American Statistician online record, `2025-10-16`. |
| S24 | Large Language Model-based Data Science Agent: A Survey | OpenReview page shows TMLR publication on `2026-02-08`. |

## Runtime Governance

- A source being verified does not make a runtime formula calibrated.
- Every runtime quantity named as a posterior, utility, or decision score must separately carry `Exact`, `Variational`, or `Operational` status metadata.
- Uncalibrated runtime surrogates are allowed in `shadow`; in `active`, they may not override the baseline until a validation report records the required metrics.

## Use

- This log exists to keep the core source set anchored in formally published or formally accepted material.
- If a future source is added to the core set, its publication status should be logged here.
- If a source is later superseded or reclassified, this log should record the change and date.
