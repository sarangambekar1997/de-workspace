# Vector Databases
> Storing, indexing, and querying embeddings at scale for RAG, semantic search, and similarity lookups.

**Prerequisites:** [Embeddings](embeddings.md)

**Related:** [RAG](rag.md) · [SQL](../00-foundations/sql-reference.md) · [Glossary](../99-reference/glossary.md)

---

## Table of Contents

**Basic**
- [Why a Vector Database](#why-a-vector-database)
- [Core Concepts](#core-concepts)
- [pgvector (PostgreSQL)](#pgvector-postgresql)

**Intermediate**
- [Pinecone](#pinecone)
- [Chroma](#chroma)
- [Weaviate](#weaviate)

**Advanced**
- [Index Types & Trade-offs](#index-types--trade-offs)
- [Filtering at Scale](#filtering-at-scale)
- [Choosing the Right Vector DB](#choosing-the-right-vector-db)
- [Production Patterns](#production-patterns)

---

## Why a Vector Database

A vector database stores embeddings and lets you find the N most similar ones to a query vector in milliseconds — even across millions of vectors.

```
Plain NumPy (brute force):   O(n) per query   — fine for < 100k vectors
Vector DB (ANN index):       O(log n) per query — millions of vectors, sub-10ms
```

**ANN = Approximate Nearest Neighbor** — trades tiny accuracy loss for massive speed gain.

Vector DBs also provide:
- Metadata storage alongside each vector (doc title, source, date, tags)
- Metadata filtering (search only vectors where `type="docs"`)
- Namespaces/collections to separate indexes
- Upsert semantics (re-index updated documents without rebuilding)
- Managed scaling (no infrastructure to run)

---

## Core Concepts

| Concept | Definition |
|---------|-----------|
| **Vector / Embedding** | A list of floats representing a document's meaning |
| **Index** | The data structure that enables fast ANN search (HNSW, IVFFlat, etc.) |
| **Namespace / Collection** | A logical partition of the index (e.g., separate namespaces per customer) |
| **Upsert** | Insert if new, update if ID already exists |
| **k-NN query** | "Find the k most similar vectors to this query vector" |
| **Metadata** | Key-value pairs stored alongside each vector, used for filtering |
| **Similarity metric** | How to measure distance: cosine, dot product, or Euclidean |

---

## pgvector (PostgreSQL)

Best choice when you already have PostgreSQL and your dataset is < a few million vectors.

```bash
# Install extension
pip install pgvector psycopg2-binary
```

```sql
-- Enable the extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create a table with an embedding column
CREATE TABLE documents (
    id          SERIAL PRIMARY KEY,
    source      TEXT NOT NULL,
    doc_type    TEXT,
    content     TEXT NOT NULL,
    embedding   vector(1536),       -- 1536 dims for text-embedding-3-small
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- IVFFlat index: good for large tables (> 1M rows)
-- lists = sqrt(num_rows) is a good starting point
CREATE INDEX ON documents USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- HNSW index: better recall, more memory, faster queries (recommended for most cases)
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

```python
import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
import numpy as np
from openai import OpenAI

openai_client = OpenAI()
conn = psycopg2.connect("postgresql://user:[REDACTED_SQL_PASSWORD_1]@localhost:5432/mydb")
register_vector(conn)

def embed_batch(texts: list[str]) -> list[list[float]]:
    response = openai_client.embeddings.create(input=texts, model="text-embedding-3-small")
    return [r.embedding for r in response.data]

# ── Insert ────────────────────────────────────────────────────────────────────
def upsert_documents(documents: list[dict]):
    """documents = [{source, doc_type, content}, ...]"""
    texts = [d["content"] for d in documents]
    vecs  = embed_batch(texts)

    with conn.cursor() as cur:
        rows = [(d["source"], d.get("doc_type"), d["content"], v)
                for d, v in zip(documents, vecs)]
        execute_values(
            cur,
            "INSERT INTO documents (source, doc_type, content, embedding) VALUES %s "
            "ON CONFLICT (source) DO UPDATE SET content=EXCLUDED.content, embedding=EXCLUDED.embedding",
            rows
        )
        conn.commit()

# ── Search ────────────────────────────────────────────────────────────────────
def search(query: str, k: int = 5, doc_type: str = None) -> list[dict]:
    q_vec = embed_batch([query])[0]

    filter_clause = "WHERE doc_type = %s" if doc_type else ""
    params = (q_vec, doc_type, k) if doc_type else (q_vec, k)

    sql = f"""
        SELECT source, doc_type, content,
               1 - (embedding <=> %s::vector) AS score
        FROM documents
        {filter_clause}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    # Fix params — query vector appears twice (score calc + ORDER BY)
    params = (q_vec, q_vec, k) if not doc_type else (q_vec, doc_type, q_vec, k)

    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [{"source": r[0], "doc_type": r[1], "content": r[2], "score": r[3]}
                for r in cur.fetchall()]

results = search("orders table schema", k=3)
for r in results:
    print(f"{r['score']:.3f}  {r['source']}")
```

---

## Pinecone

Managed vector database — no infrastructure, scales to billions of vectors.

```bash
pip install pinecone-client
```

```python
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI

pc     = Pinecone(api_key="YOUR_PINECONE_API_KEY")
client = OpenAI()

# ── Create an index ────────────────────────────────────────────────────────────
pc.create_index(
    name="de-knowledge-base",
    dimension=1536,       # must match your embedding model
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1")
)

index = pc.Index("de-knowledge-base")

# ── Upsert vectors ─────────────────────────────────────────────────────────────
documents = [
    {"id": "orders-schema", "text": "The orders table has order_id, customer_id, amount, status, created_at", "type": "schema"},
    {"id": "kafka-intro",   "text": "Kafka is a distributed event streaming platform", "type": "docs"},
]

def embed(texts):
    r = client.embeddings.create(input=texts, model="text-embedding-3-small")
    return [x.embedding for x in r.data]

vecs = embed([d["text"] for d in documents])

vectors = [
    {
        "id":       doc["id"],
        "values":   vec,
        "metadata": {"text": doc["text"], "type": doc["type"]}
    }
    for doc, vec in zip(documents, vecs)
]
index.upsert(vectors=vectors, namespace="default")

# ── Query ──────────────────────────────────────────────────────────────────────
query_vec = embed(["what columns does the orders table have?"])[0]

results = index.query(
    vector=query_vec,
    top_k=3,
    include_metadata=True,
    namespace="default",
    filter={"type": {"$eq": "schema"}}   # metadata filter
)

for match in results.matches:
    print(f"{match.score:.3f}  {match.id}  {match.metadata['text'][:80]}")

# ── Update / Delete ────────────────────────────────────────────────────────────
# Update a vector (upsert with same ID)
index.upsert(vectors=[{"id": "orders-schema", "values": new_vec, "metadata": {...}}])

# Delete by ID
index.delete(ids=["orders-schema"], namespace="default")

# Delete by metadata filter
index.delete(filter={"type": {"$eq": "stale"}}, namespace="default")

# Stats
print(index.describe_index_stats())
```

---

## Chroma

Open-source, embeds natively in Python — great for local development and smaller production workloads.

```bash
pip install chromadb
```

```python
import chromadb
from chromadb.utils import embedding_functions

# ── Local (in-memory or persistent) ───────────────────────────────────────────
client = chromadb.Client()                             # in-memory
client = chromadb.PersistentClient(path="./chroma_db") # persists to disk

# ── Use OpenAI embeddings ──────────────────────────────────────────────────────
oai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key="YOUR_OPENAI_API_KEY",
    model_name="text-embedding-3-small"
)

collection = client.create_collection(
    name="de_knowledge_base",
    embedding_function=oai_ef,
    metadata={"hnsw:space": "cosine"}
)

# ── Add documents (Chroma embeds automatically) ────────────────────────────────
collection.add(
    ids=["doc1", "doc2", "doc3"],
    documents=[
        "The orders table has order_id, customer_id, amount, status",
        "Airflow is a workflow orchestration tool using DAGs",
        "Kafka is a distributed event streaming platform",
    ],
    metadatas=[
        {"type": "schema",  "team": "data"},
        {"type": "docs",    "team": "data"},
        {"type": "docs",    "team": "platform"},
    ]
)

# ── Query ──────────────────────────────────────────────────────────────────────
results = collection.query(
    query_texts=["orders table columns"],
    n_results=3,
    where={"type": {"$eq": "schema"}},   # metadata filter
)

for doc, meta, dist in zip(results["documents"][0],
                           results["metadatas"][0],
                           results["distances"][0]):
    print(f"dist={dist:.3f}  type={meta['type']}  {doc[:80]}")

# ── Update / Delete ────────────────────────────────────────────────────────────
collection.update(ids=["doc1"], documents=["Updated orders schema text"])
collection.delete(ids=["doc2"])
collection.upsert(ids=["doc4"], documents=["New document"])

print(collection.count())  # number of documents
```

---

## Weaviate

Open-source, production-grade, supports multi-modal embeddings and GraphQL.

```bash
pip install weaviate-client
# Run: docker run -p 8080:8080 semitechnologies/weaviate:latest
```

```python
import weaviate
from weaviate.classes.init import Auth

# Local
client = weaviate.connect_to_local()

# Cloud
client = weaviate.connect_to_weaviate_cloud(
    cluster_url="YOUR_WCS_URL",
    auth_credentials=Auth.api_key("YOUR_WCS_API_KEY"),
)

# ── Create collection (schema) ─────────────────────────────────────────────────
from weaviate.classes.config import Configure, Property, DataType

client.collections.create(
    name="Document",
    vectorizer_config=Configure.Vectorizer.text2vec_openai(model="text-embedding-3-small"),
    properties=[
        Property(name="content",  data_type=DataType.TEXT),
        Property(name="doc_type", data_type=DataType.TEXT),
        Property(name="source",   data_type=DataType.TEXT),
    ]
)

collection = client.collections.get("Document")

# ── Insert ─────────────────────────────────────────────────────────────────────
from weaviate.classes.data import DataObject

collection.data.insert_many([
    DataObject(properties={"content": "The orders table has order_id, amount, status",
                            "doc_type": "schema", "source": "data_dict"}),
    DataObject(properties={"content": "Airflow orchestrates pipelines as DAGs",
                            "doc_type": "docs", "source": "wiki"}),
])

# ── Semantic search ────────────────────────────────────────────────────────────
from weaviate.classes.query import MetadataQuery, Filter

results = collection.query.near_text(
    query="orders table columns",
    limit=3,
    filters=Filter.by_property("doc_type").equal("schema"),
    return_metadata=MetadataQuery(certainty=True)
)

for obj in results.objects:
    print(f"{obj.metadata.certainty:.3f}  {obj.properties['content'][:80]}")

# ── Hybrid search (BM25 + vector) ─────────────────────────────────────────────
results = collection.query.hybrid(
    query="orders table",
    alpha=0.5,   # 0=BM25, 1=vector
    limit=5
)

client.close()
```

---

## Index Types & Trade-offs

| Index | Algorithm | Speed | Recall | Memory | Notes |
|-------|-----------|-------|--------|--------|-------|
| **Flat** | Brute force | Slow | 100% | Low | Only for < 100k vectors |
| **IVFFlat** | Inverted file | Fast | 95–99% | Medium | Good for > 1M vectors |
| **HNSW** | Hierarchical graph | Very fast | 95–99% | High | Best for most use cases |
| **ScaNN** | Google's ANN | Very fast | 99%+ | Medium | Production at Google scale |

```sql
-- pgvector: HNSW (recommended default)
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
-- m: connections per node (16 is default; higher = better recall, more memory)
-- ef_construction: build-time quality (64 is default; higher = slower build, better index)

-- At query time:
SET hnsw.ef_search = 40;  -- higher = better recall, slower query (default 40)
```

---

## Filtering at Scale

The challenge: metadata filters can't use the ANN index — they degrade to brute force.

**Solutions:**

```python
# 1. Pre-filter then search (fast but can miss results)
# Pinecone, Weaviate, Chroma support this natively

# 2. Post-filter (search k*10, then filter down to k)
def search_with_post_filter(query: str, k: int, doc_type: str, overfetch: int = 10):
    candidates = search(query, k=k * overfetch)
    filtered   = [c for c in candidates if c["doc_type"] == doc_type]
    return filtered[:k]

# 3. Namespaces — separate index per filter value
# e.g., one Pinecone namespace per team or customer
index.query(vector=q_vec, top_k=5, namespace="team_data")
index.query(vector=q_vec, top_k=5, namespace="team_platform")
```

---

## Choosing the Right Vector DB

| | pgvector | Chroma | Pinecone | Weaviate |
|-|----------|--------|----------|----------|
| **Managed** | No | No | Yes | Yes/No |
| **Scale** | ~10M | ~1M | Billions | Billions |
| **Setup** | Need Postgres | Python-native | API key | Docker/Cloud |
| **Cost** | Postgres infra | Free | Paid | Free/Paid |
| **Best for** | Existing PG, < 5M | Local dev, small prod | Serverless, large scale | Multi-modal, graph queries |
| **Hybrid search** | Manual | No | No | Yes |
| **Multi-modal** | No | No | No | Yes |

**Decision guide:**
- Already have PostgreSQL → **pgvector**
- Local development / prototyping → **Chroma**
- Production, don't want to manage infra → **Pinecone**
- Need hybrid search or multi-modal → **Weaviate**

---

## Production Patterns

### Incremental indexing

```python
import hashlib

def get_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]

def sync_documents(new_docs: list[dict], index, existing_ids: set):
    """Only upsert documents that are new or changed."""
    to_upsert = []
    for doc in new_docs:
        doc_id = f"{doc['source']}_{get_content_hash(doc['content'])}"
        if doc_id not in existing_ids:
            to_upsert.append({**doc, "id": doc_id})

    if to_upsert:
        texts = [d["content"] for d in to_upsert]
        vecs  = embed_batch(texts)
        index.upsert(vectors=[
            {"id": d["id"], "values": v, "metadata": {"content": d["content"], "source": d["source"]}}
            for d, v in zip(to_upsert, vecs)
        ])
    print(f"Synced {len(to_upsert)} new/changed documents")
```

### Namespace-per-tenant (multi-tenancy)

```python
def get_user_index(user_id: str):
    """Each user/team gets their own namespace — complete isolation."""
    return lambda **kwargs: index.query(namespace=f"user_{user_id}", **kwargs)

def upsert_for_user(user_id: str, documents: list[dict]):
    index.upsert(vectors=vectors, namespace=f"user_{user_id}")
```

### Cache frequent queries

```python
import hashlib
from functools import lru_cache

@lru_cache(maxsize=1000)
def cached_search(query: str, k: int = 5) -> tuple:
    results = search(query, k=k)
    return tuple(frozenset(r.items()) for r in results)
```

### Monitor index health

```python
def index_health_check(index) -> dict:
    stats = index.describe_index_stats()
    return {
        "total_vectors":      stats.total_vector_count,
        "namespaces":         list(stats.namespaces.keys()),
        "index_fullness_pct": stats.index_fullness * 100,
    }

# Alert if index is >80% full (Pinecone pods have limits)
health = index_health_check(index)
if health["index_fullness_pct"] > 80:
    print("WARNING: index is >80% full — consider scaling")
```

---

**Previous:** [RAG](rag.md) · **Next:** [AI Agents](ai-agents.md) · **Back to:** [Index](../README.md)
