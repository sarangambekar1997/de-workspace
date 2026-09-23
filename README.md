# Data Engineering Bible

All of my data engineering knowledge in one place: concepts, tools, and production patterns,
from first query to production pipelines, plus the AI/LLM engineering that now sits alongside them.

Every guide goes **Basic → Intermediate → Advanced** with working code examples.

**→ Read it as a website: [sarangambekar1997.github.io/de-workspace](https://sarangambekar1997.github.io/de-workspace/)** — searchable, with navigation and dark mode

**→ Or start here on GitHub: [Full index & learning paths](docs/README.md)**

---

## Layout

| Folder | Covers |
|--------|--------|
| [`docs/00-foundations`](docs/00-foundations) | DE concepts, SQL, Python, Linux & Bash, Git |
| [`docs/01-storage`](docs/01-storage) | Cloud storage, data modeling, Snowflake, BigQuery, Redshift, Apache Iceberg |
| [`docs/02-processing`](docs/02-processing) | Data ingestion & CDC, DuckDB & Polars, PySpark, Databricks, dbt |
| [`docs/03-orchestration`](docs/03-orchestration) | Apache Airflow |
| [`docs/04-streaming`](docs/04-streaming) | Apache Kafka, Apache Flink |
| [`docs/05-quality-governance`](docs/05-quality-governance) | Data quality, governance, lineage, contracts |
| [`docs/06-infrastructure`](docs/06-infrastructure) | Docker, Terraform |
| [`docs/07-ai`](docs/07-ai) | Prompting, LLM APIs, embeddings, RAG, vector DBs, agents, evals, MLflow, fine-tuning |
| [`docs/08-architecture`](docs/08-architecture) | System design, cost optimization |
| [`docs/99-reference`](docs/99-reference) | Glossary |

Folders are numbered roughly in learning order. New topics go in the folder that matches
where they sit in a pipeline, and a new top-level area gets the next free number.

## Where to start

| If you are… | Read |
|-------------|------|
| New to data engineering | [DE Concepts](docs/00-foundations/de-concepts.md) → [SQL](docs/00-foundations/sql-reference.md) → [Python](docs/00-foundations/python-reference.md) |
| Focused on the warehouse | A warehouse ([Snowflake](docs/01-storage/snowflake-reference.md) / [BigQuery](docs/01-storage/bigquery-reference.md) / [Redshift](docs/01-storage/redshift-reference.md)) → [dbt](docs/02-processing/dbt-reference.md) → [Data Quality](docs/05-quality-governance/data-quality.md) |
| Focused on big data | [PySpark](docs/02-processing/pyspark-reference.md) → [Databricks](docs/02-processing/databricks-reference.md) → [Kafka](docs/04-streaming/kafka-reference.md) |
| Building with LLMs | [Prompt Engineering](docs/07-ai/prompt-engineering.md) → [LLM APIs](docs/07-ai/llm-apis.md) → [RAG](docs/07-ai/rag.md) |
| Preparing for design interviews | [System Design](docs/08-architecture/system-design.md) → [Ingestion & CDC](docs/02-processing/ingestion-cdc.md) → [Data Modeling](docs/01-storage/data-modeling.md) |
| Looking up a term | [Glossary](docs/99-reference/glossary.md) |

The full learning paths, the "when should I use what" tables, and the cheat sheets are in the [index](docs/README.md).

## Writing a new guide

Copy [`docs/_template.md`](docs/_template.md). Every guide uses the same sections:

1. Prerequisites / Related links at the top
2. Overview (the problem the topic solves and how, before any code)
3. Table of contents split into Basic / Intermediate / Advanced
4. Content sections with runnable code
5. Common Pitfalls
6. Cheat Sheet
7. Interview Questions
8. Further Reading
9. Next / Back navigation at the bottom

Then add the guide to [`docs/README.md`](docs/README.md), to any learning path it belongs in, and to the `nav` section of [`mkdocs.yml`](mkdocs.yml).

## Previewing the site locally

```bash
pip install -r requirements-docs.txt
mkdocs serve                 # live preview at http://127.0.0.1:8000
mkdocs build --strict        # the same check CI runs: fails on broken links or anchors
```

Pull requests that touch `docs/` are built in strict mode by CI; merges to `main` deploy the site to GitHub Pages.
