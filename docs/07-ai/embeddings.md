# Embeddings
> Turning text (and other data) into vectors for semantic search, clustering, classification, and RAG.

**Prerequisites:** [LLM APIs](llm-apis.md)

**Related:** [RAG](rag.md) · [Vector Databases](vector-databases.md) · [Glossary](../99-reference/glossary.md)

---

## Table of Contents

**Basic**
- [What Are Embeddings](#what-are-embeddings)
- [Generating Embeddings](#generating-embeddings)
- [Cosine Similarity](#cosine-similarity)

**Intermediate**
- [Choosing an Embedding Model](#choosing-an-embedding-model)
- [Embedding in Batches](#embedding-in-batches)
- [Semantic Search Without a Vector DB](#semantic-search-without-a-vector-db)
- [Chunking Text for Embeddings](#chunking-text-for-embeddings)

**Advanced**
- [Use Cases Beyond RAG](#use-cases-beyond-rag)
- [Fine-Tuning Embeddings](#fine-tuning-embeddings)
- [Storing Embeddings at Scale](#storing-embeddings-at-scale)
- [Embedding Pipelines in Production](#embedding-pipelines-in-production)

---

## What Are Embeddings

An embedding is a vector (list of floats) that represents the semantic meaning of a piece of text. Texts with similar meanings have vectors that are close together in space.

```
"How many orders were placed today?"      → [0.021, -0.143, 0.087, ...]  (1536 dims)
"What is today's order count?"            → [0.019, -0.141, 0.091, ...]  (very close)
"The capital of France is Paris"          → [-0.432, 0.201, -0.055, ...] (far away)
```

**What embeddings capture:**
- Semantic similarity (not just keyword overlap)
- "dog" and "canine" are close; "dog" and "cat" are closer than "dog" and "table"
- Context and intent, not just surface form

**Where embeddings are used:**
- **RAG**: find relevant documents to give to an LLM
- **Semantic search**: search by meaning, not keywords
- **Deduplication**: find near-duplicate records
- **Clustering**: group similar items
- **Classification**: classify text by proximity to class examples
- **Anomaly detection**: flag records far from normal

---

## Generating Embeddings

```python
# OpenAI
from openai import OpenAI
import numpy as np

client = OpenAI()

def embed(texts: list[str], model="text-embedding-3-small") -> np.ndarray:
    response = client.embeddings.create(
        input=texts,
        model=model
    )
    return np.array([r.embedding for r in response.data])

# Single text
vec = embed(["What is Apache Kafka?"])[0]
print(f"Dimensions: {len(vec)}")    # 1536 for text-embedding-3-small

# Multiple texts at once (up to 2048 in one call)
vecs = embed([
    "Apache Kafka is a distributed event streaming platform",
    "Snowflake is a cloud data warehouse",
    "dbt transforms data in the warehouse",
])
print(f"Shape: {vecs.shape}")   # (3, 1536)
```

```python
# Anthropic (via Voyage AI — Anthropic's embedding partner)
# pip install voyageai
import voyageai

vo = voyageai.Client()   # reads VOYAGE_API_KEY

result = vo.embed(
    ["Apache Kafka is a distributed event streaming platform"],
    model="voyage-3",
    input_type="document"
)
vec = result.embeddings[0]
print(len(vec))   # 1024
```

```python
# Sentence Transformers — free, runs locally
# pip install sentence-transformers
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")   # 384 dims, fast
vecs = model.encode([
    "Apache Kafka is a distributed event streaming platform",
    "Snowflake is a cloud data warehouse",
])
print(vecs.shape)   # (2, 384)
```

---

## Cosine Similarity

The most common way to measure how similar two embeddings are.

```python
import numpy as np

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# Range: -1 (opposite) to 1 (identical)
# In practice with text embeddings: 0.7+ is similar, 0.9+ is very similar

query   = embed(["What is Kafka?"])[0]
doc1    = embed(["Apache Kafka is a distributed event streaming platform"])[0]
doc2    = embed(["The Eiffel Tower is in Paris"])[0]

print(cosine_similarity(query, doc1))   # ~0.87
print(cosine_similarity(query, doc2))   # ~0.22
```

```python
# Batch similarity: query vs many documents
def top_k_similar(query_vec: np.ndarray, doc_vecs: np.ndarray, k: int = 5) -> list[int]:
    # Normalize all vectors
    q = query_vec / np.linalg.norm(query_vec)
    D = doc_vecs / np.linalg.norm(doc_vecs, axis=1, keepdims=True)
    scores = D @ q  # dot product = cosine similarity for normalized vectors
    return np.argsort(scores)[::-1][:k].tolist()
```

---

## Choosing an Embedding Model

| Model | Dims | Speed | Cost | Best for |
|-------|------|-------|------|----------|
| `text-embedding-3-small` (OpenAI) | 1536 | Fast | Low | General purpose, RAG |
| `text-embedding-3-large` (OpenAI) | 3072 | Medium | Medium | High-accuracy retrieval |
| `voyage-3` (Voyage AI) | 1024 | Fast | Low | General, Anthropic ecosystem |
| `voyage-3-large` (Voyage AI) | 1024 | Medium | Medium | High-accuracy retrieval |
| `all-MiniLM-L6-v2` (local) | 384 | Very fast | Free | Prototyping, offline |
| `bge-large-en` (local) | 1024 | Medium | Free | Production on-prem |

**Tips:**
- Start with `text-embedding-3-small` — it's fast and good enough for most RAG
- Only upgrade to `large` if retrieval quality is measurably worse
- Local models (sentence-transformers) are great for prototyping and cost-sensitive workloads
- Normalize vectors before storing — speeds up dot-product search

---

## Embedding in Batches

```python
from openai import OpenAI
import numpy as np
import time

client = OpenAI()

def embed_large_dataset(texts: list[str], batch_size: int = 500) -> np.ndarray:
    """Embed a large list of texts efficiently in batches."""
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        # Remove newlines — they can hurt embedding quality
        batch = [t.replace("\n", " ") for t in batch]

        response = client.embeddings.create(
            input=batch,
            model="text-embedding-3-small"
        )
        batch_embeddings = [r.embedding for r in response.data]
        all_embeddings.extend(batch_embeddings)

        if i % 5000 == 0:
            print(f"Embedded {i}/{len(texts)}")
        time.sleep(0.1)  # gentle rate limiting

    return np.array(all_embeddings)
```

---

## Semantic Search Without a Vector DB

For small datasets (< 100k), skip the vector DB and use numpy directly.

```python
import numpy as np
import json
from openai import OpenAI

client = OpenAI()

# Build an in-memory index
documents = [
    "Kafka is used for real-time event streaming",
    "dbt transforms data in the warehouse using SQL",
    "Airflow orchestrates data pipelines as DAGs",
    "Snowflake is a cloud-native data warehouse",
    "Delta Lake adds ACID transactions to data lakes",
]

print("Building embeddings index...")
doc_embeddings = embed_large_dataset(documents)
doc_embeddings = doc_embeddings / np.linalg.norm(doc_embeddings, axis=1, keepdims=True)

# Save to disk
np.save("embeddings.npy", doc_embeddings)
with open("documents.json", "w") as f:
    json.dump(documents, f)

# Search
def search(query: str, k: int = 3) -> list[dict]:
    q_vec = embed([query])[0]
    q_vec = q_vec / np.linalg.norm(q_vec)
    scores = doc_embeddings @ q_vec
    top_k = np.argsort(scores)[::-1][:k]
    return [{"text": documents[i], "score": float(scores[i])} for i in top_k]

results = search("how do I schedule a data pipeline?")
for r in results:
    print(f"{r['score']:.3f}  {r['text']}")
# 0.821  Airflow orchestrates data pipelines as DAGs
# 0.612  dbt transforms data in the warehouse using SQL
# 0.543  Kafka is used for real-time event streaming
```

---

## Chunking Text for Embeddings

Long documents must be split into chunks before embedding. The chunk strategy dramatically affects retrieval quality.

```python
from typing import Generator

def chunk_by_tokens(text: str, max_tokens: int = 512, overlap: int = 50) -> list[str]:
    """
    Split text into overlapping chunks.
    overlap: tokens shared between adjacent chunks — preserves context at boundaries.
    """
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + max_tokens
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += max_tokens - overlap
    return chunks

def chunk_by_paragraph(text: str, max_chars: int = 1000) -> list[str]:
    """Split on paragraph breaks, merge short paragraphs."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) < max_chars:
            current += "\n\n" + para if current else para
        else:
            if current:
                chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    return chunks

def chunk_markdown_by_section(text: str) -> list[dict]:
    """Split markdown on ## headings, preserving section title."""
    import re
    sections = re.split(r'\n(?=##\s)', text)
    return [
        {"title": s.split("\n")[0].strip("# "), "content": s}
        for s in sections if s.strip()
    ]
```

**Chunking rules:**
- 256–512 tokens is a good starting point for most RAG
- Overlap of 10–20% helps context at chunk boundaries
- Never split mid-sentence
- Add document metadata (title, source URL, section) to each chunk before embedding
- Prefer semantic splits (paragraphs, sections) over fixed-size splits

---

## Use Cases Beyond RAG

### Semantic deduplication

```python
def find_duplicates(texts: list[str], threshold: float = 0.95) -> list[tuple[int, int, float]]:
    vecs = embed(texts)
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    sims = vecs @ vecs.T
    dupes = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if sims[i, j] > threshold:
                dupes.append((i, j, float(sims[i, j])))
    return dupes
```

### Zero-shot classification via embeddings

```python
def classify(text: str, labels: list[str]) -> str:
    """Classify text by finding the closest label embedding."""
    text_vec   = embed([text])[0]
    label_vecs = embed(labels)
    sims = [cosine_similarity(text_vec, lv) for lv in label_vecs]
    return labels[np.argmax(sims)]

classify("pipeline failed: connection timeout", ["error", "warning", "info"])
# → "error"
```

### Clustering

```python
from sklearn.cluster import KMeans

vecs = embed(log_messages)
kmeans = KMeans(n_clusters=10, random_state=42)
labels = kmeans.fit_predict(vecs)

# Each cluster = a class of log messages
for cluster_id in range(10):
    examples = [log_messages[i] for i, l in enumerate(labels) if l == cluster_id][:3]
    print(f"\nCluster {cluster_id}:")
    for e in examples:
        print(f"  {e}")
```

---

## Fine-Tuning Embeddings

When off-the-shelf embeddings don't capture your domain well (e.g., proprietary table names, internal jargon).

```python
# Using sentence-transformers with custom training data
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader

# Training pairs: (query, positive_doc, negative_doc)
train_examples = [
    InputExample(texts=["orders table", "fct_orders contains one row per order", "dim_customer contains customer data"]),
    InputExample(texts=["daily revenue", "SELECT SUM(amount) FROM orders GROUP BY date", "SELECT * FROM customers"]),
]

model = SentenceTransformer("all-MiniLM-L6-v2")
loader = DataLoader(train_examples, shuffle=True, batch_size=16)
loss = losses.TripletLoss(model)

model.fit(train_objectives=[(loader, loss)], epochs=3, warmup_steps=100)
model.save("./my_domain_embeddings")
```

---

## Storing Embeddings at Scale

For large datasets (> 100k vectors), persist embeddings rather than recomputing.

```python
# Store in Parquet (simplest)
import pandas as pd
import numpy as np

def save_embeddings(texts: list[str], embeddings: np.ndarray, path: str):
    df = pd.DataFrame({
        "text": texts,
        "embedding": [e.tolist() for e in embeddings]
    })
    df.to_parquet(path, index=False)

def load_embeddings(path: str) -> tuple[list[str], np.ndarray]:
    df = pd.read_parquet(path)
    texts = df["text"].tolist()
    vecs  = np.array(df["embedding"].tolist())
    return texts, vecs
```

```python
# Store in PostgreSQL with pgvector
# pip install psycopg2-binary pgvector
import psycopg2
from pgvector.psycopg2 import register_vector

conn = psycopg2.connect("postgresql://user:pass@localhost/db")
register_vector(conn)

with conn.cursor() as cur:
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id         SERIAL PRIMARY KEY,
            source     TEXT,
            content    TEXT,
            embedding  vector(1536)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS emb_idx ON embeddings USING ivfflat (embedding vector_cosine_ops)")
    conn.commit()

# Insert
def upsert_embedding(cur, source: str, content: str, vec: list[float]):
    cur.execute(
        "INSERT INTO embeddings (source, content, embedding) VALUES (%s, %s, %s)",
        (source, content, vec)
    )

# Search
def search_pgvector(cur, query_vec: list[float], k: int = 5) -> list[dict]:
    cur.execute(
        "SELECT source, content, 1 - (embedding <=> %s::vector) AS score FROM embeddings ORDER BY embedding <=> %s::vector LIMIT %s",
        (query_vec, query_vec, k)
    )
    return [{"source": r[0], "content": r[1], "score": r[2]} for r in cur.fetchall()]
```

---

## Embedding Pipelines in Production

```python
# Incremental embedding pipeline — only embed new/changed documents
import hashlib
import json

def content_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()

class IncrementalEmbeddingPipeline:
    def __init__(self, store):
        self.store = store  # dict or DB that maps hash → embedding

    def embed_new(self, documents: list[dict]) -> list[dict]:
        """Only embed documents whose content has changed."""
        to_embed   = []
        from_cache = []

        for doc in documents:
            h = content_hash(doc["content"])
            if h in self.store:
                from_cache.append({**doc, "embedding": self.store[h], "cached": True})
            else:
                to_embed.append({**doc, "hash": h})

        if to_embed:
            texts = [d["content"] for d in to_embed]
            vecs  = embed_large_dataset(texts)
            for doc, vec in zip(to_embed, vecs):
                self.store[doc["hash"]] = vec.tolist()
                from_cache.append({**doc, "embedding": vec.tolist(), "cached": False})

        print(f"Embedded: {len(to_embed)} new, {len(from_cache) - len(to_embed)} cached")
        return from_cache
```

---

**Previous:** [LLM APIs](llm-apis.md) · **Next:** [RAG](rag.md) · **Back to:** [Index](../README.md)
