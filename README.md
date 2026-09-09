# SARAI: Sovereignty-Aware Risk Assessment Infrastructure for Enterprise Business Intelligence

A five-layer Business Intelligence framework that enables natural-language querying of federated multi-engine databases while preserving data sovereignty and enabling proactive AI risk assessment.

## Architecture

| Layer | Component | Purpose |
|-------|-----------|---------|
| L1 — Data Sources | PostgreSQL + MariaDB + In-Memory Cache | 25 tables, 2.7M rows across 5 domains |
| L2 — Workflow | Workflow Orchestration Platform + SARAI Risk Pipeline | ETL orchestration and 4-mechanism risk assessment |
| L3 — Federation | Federation Engine | Cross-engine SQL federation with cost-based optimizer |
| L4 — Visualization | Dashboard Platform | RBAC dashboards with 40+ chart types |
| L5 — AI Enhancement | Local Inference Engine + Cloud API Gateway | Sovereignty-aware NL-to-SQL routing |

## Data Domains

- **E-Commerce** — Brazilian Olist marketplace (9 tables, 830K+ orders)
- **Healthcare** — Hospital admissions and insurance (5 tables)
- **Financial** — Credit card fraud detection (3 tables)
- **Retail** — UK online retail invoices (3 tables)
- **Supply Chain** — DataCo global supply chain (5 tables)

## Key Results

| Model | Parameters | Location | Accuracy | σ_I | ρ_max |
|-------|-----------|----------|----------|-----|-------|
| Llama 3.2 | 3B | Local | 46% | 1.0 | 1.0 |
| Llama 3.1 | 8B | Local | 60% | 1.0 | 1.0 |
| Gemma-3 | 27B | Cloud | 90% | 0.0 | 0.0 |
| DeepSeek R1 | 671B | Cloud | 78% | 0.0 | 0.0 |

- **Anomaly Scorer**: Precision=1.000, Recall=0.960, F1=0.980
- **Statistical significance**: McNemar's exact tests with Holm--Bonferroni correction and Cochran's Q test are reported for the four paired model outcomes.

## Risk Mechanisms (Algorithm 2)

1. **SQL Anomaly Scorer** — 13-rule heuristic detecting injection, hallucinated columns, catalog probing, structural anomalies
2. **Confidence Gate** — A deployed rule-based confidence proxy over generated SQL
3. **Schema Drift Monitor** — Detects DDL changes between inference and execution
4. **Sovereignty Constraint** — Enforces σ_D ≥ τ_D for data residency compliance

## Paper 2: RAG-SQL

The companion study introduces RAG-SQL, a retrieval-augmented generation framework for sovereignty-aware text-to-SQL in federated environments.

| Strategy | Avg Tokens | 3B Acc | 8B Acc | Cloud Acc |
|----------|-----------|--------|--------|--------|
| Few-shot (baseline) | ~4,200 | 46% | 60% | 90% (27B) |
| Naïve RAG | 424 | 30% | 38% | 70% (12B) |
| Enhanced RAG | 670 | 36% | 30% | 68% (12B) |

- **89.9% prompt schema reduction** (4,200 → 424 tokens)
- **300 experimental configurations** (50 queries × 3 models × 2 RAG strategies)

See papers/Paper2/Elsevier-IPM for benchmark code and raw results.

## Repository Structure

```
papers/Paper1/Springer-Nature/       Paper 1 manuscript + figures
papers/Paper1/MDPI-AppliedSciences/  Paper 1 MDPI package
papers/Paper2/Elsevier-IPM/          Paper 2 RAG-SQL code, results, and LaTeX sources
papers/Paper2/MDPI-AppliedSciences/  Paper 2 MDPI package
papers/Paper2/RAG-Workspace/         Paper 2 additional RAG workspace
framework/                           Python implementation (risk mechanisms, benchmarks, deployment)
datasets/metadata/                   Dataset provenance metadata and source links

The repository intentionally excludes credentials, raw datasets, generated
benchmark outputs, local caches, and server logs. The benchmark scripts read
connection settings from environment variables; see the scripts' configuration
names and do not commit a local `.env` file.

The manuscript and supplementary response are maintained with the paper files
in the author's working environment. The code repository for this study is the
private GitHub repository:
https://github.com/WganMe/sarai-framework
```

## Deployment

The framework runs on a dedicated server (8 vCPU, 32GB RAM, 500GB NVMe SSD). See papers/Project/framework/deploy_framework_workflow.py for automated deployment.

## Citation

```bibtex
@article{author2026sarai,
  title={SARAI: Sovereignty-Aware Risk Assessment Infrastructure for Enterprise Business Intelligence},
  author={[Author 1] and [Author 2] and [Author 3]},
  journal={Under Review},
  year={2026}
}

@article{author2026ragsql,
  title={RAG-SQL: Sovereignty-Aware Retrieval-Augmented Generation for Text-to-SQL in Federated Database Environments},
  author={[Author 1] and [Author 2] and [Author 3]},
  journal={Under Review},
  year={2026}
}
```

## License

This project is part of a PhD dissertation at King Abdulaziz University (KAU), Faculty of Computing and Information Technology (FCIT).
