# LangChain & LlamaIndex
> Frameworks for building RAG pipelines, agents, and LLM applications with less boilerplate.

---

## Table of Contents

**Basic**
- [LangChain vs LlamaIndex vs Raw SDK](#langchain-vs-llamaindex-vs-raw-sdk)
- [LangChain Setup](#langchain-setup)
- [LangChain Basics](#langchain-basics)

**Intermediate**
- [LangChain RAG Pipeline](#langchain-rag-pipeline)
- [LangChain Agents](#langchain-agents)
- [LlamaIndex Setup](#llamaindex-setup)
- [LlamaIndex RAG Pipeline](#llamaindex-rag-pipeline)

**Advanced**
- [LangChain Expression Language (LCEL)](#langchain-expression-language-lcel)
- [Custom Retrievers](#custom-retrievers)
- [LangSmith (Tracing & Evals)](#langsmith-tracing--evals)
- [When to Use a Framework vs Raw SDK](#when-to-use-a-framework-vs-raw-sdk)

---

## LangChain vs LlamaIndex vs Raw SDK

| | LangChain | LlamaIndex | Raw SDK |
|-|-----------|------------|---------|
| **Best for** | Chains, agents, flexible pipelines | RAG, document Q&A, knowledge bases | Full control, production, simple use cases |
| **RAG** | Good | Excellent | Manual but transparent |
| **Agents** | Excellent | Good | Manual via tool use |
| **Learning curve** | Steep | Medium | Low |
| **Abstraction level** | High | High | Low |
| **Vendor lock-in** | Some | Some | None |
| **When to choose** | Complex agent workflows | Document Q&A, data indexing | Most production use cases |

**Recommendation:** Start with the raw SDK. Add a framework only when you're writing the same boilerplate repeatedly.

---

## LangChain Setup

```bash
pip install langchain langchain-anthropic langchain-openai langchain-community
pip install faiss-cpu                  # local vector store
pip install langchain-chroma           # Chroma vector store
```

```python
# LangChain works with both providers
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

llm        = ChatAnthropic(model="claude-sonnet-5")
llm_openai = ChatOpenAI(model="gpt-4o")
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
```

---

## LangChain Basics

### Invoke a model

```python
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

llm = ChatAnthropic(model="claude-sonnet-5")

# Simple call
response = llm.invoke("What is Apache Kafka?")
print(response.content)

# With system message
messages = [
    SystemMessage(content="You are a concise data engineering expert."),
    HumanMessage(content="What is Apache Kafka?"),
]
response = llm.invoke(messages)
print(response.content)
```

### Prompt templates

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an expert in {domain}. Be concise."),
    ("human",  "{question}"),
])

chain = prompt | llm
response = chain.invoke({"domain": "data engineering", "question": "What is a DAG?"})
print(response.content)
```

### Output parsers

```python
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.pydantic_v1 import BaseModel

# String output
chain = prompt | llm | StrOutputParser()
result = chain.invoke({"domain": "SQL", "question": "Explain a CTE"})
print(result)  # plain string

# Structured JSON output
class PipelineInfo(BaseModel):
    name:        str
    schedule:    str
    source:      str
    destination: str

parser = JsonOutputParser(pydantic_object=PipelineInfo)

structured_prompt = ChatPromptTemplate.from_messages([
    ("system", "Extract pipeline info as JSON. {format_instructions}"),
    ("human",  "{text}"),
]).partial(format_instructions=parser.get_format_instructions())

chain = structured_prompt | llm | parser
result = chain.invoke({"text": "Nightly Stripe→Snowflake job at 2am UTC"})
print(result)  # PipelineInfo(name=..., schedule=..., ...)
```

---

## LangChain RAG Pipeline

```python
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

# ── 1. Load documents ─────────────────────────────────────────────────────────
loader = DirectoryLoader("./docs/", glob="**/*.md", loader_cls=TextLoader)
docs   = loader.load()
print(f"Loaded {len(docs)} documents")

# ── 2. Split into chunks ──────────────────────────────────────────────────────
splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    separators=["\n\n", "\n", " ", ""]
)
chunks = splitter.split_documents(docs)
print(f"Split into {len(chunks)} chunks")

# ── 3. Embed and store ────────────────────────────────────────────────────────
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vectorstore = Chroma.from_documents(
    documents=chunks,
    embedding=embeddings,
    persist_directory="./chroma_db"
)

# ── 4. Create retriever ───────────────────────────────────────────────────────
retriever = vectorstore.as_retriever(
    search_type="similarity",
    search_kwargs={"k": 5}
)

# ── 5. Build RAG chain ────────────────────────────────────────────────────────
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

prompt = ChatPromptTemplate.from_template("""
Answer based only on the context below.
If the answer isn't there, say "I don't have that information."

Context:
{context}

Question: {question}
""")

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

# ── 6. Ask questions ──────────────────────────────────────────────────────────
answer = rag_chain.invoke("What is the medallion architecture?")
print(answer)

# Stream
for chunk in rag_chain.stream("Explain PySpark window functions"):
    print(chunk, end="", flush=True)
```

### With metadata filtering

```python
from langchain_community.vectorstores import Chroma

retriever = vectorstore.as_retriever(
    search_type="similarity",
    search_kwargs={
        "k": 5,
        "filter": {"source": "docs/pyspark-reference.md"}  # Chroma metadata filter
    }
)
```

---

## LangChain Agents

```python
from langchain_anthropic import ChatAnthropic
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

# ── Define tools with @tool decorator ─────────────────────────────────────────
@tool
def run_sql(query: str) -> str:
    """Execute a SQL SELECT query against the data warehouse. Returns results as JSON."""
    # Simulated
    return '{"rows": [{"count": 152340}]}'

@tool
def get_table_schema(table_name: str) -> str:
    """Get the schema (columns and types) for a given table."""
    schemas = {
        "orders": "order_id VARCHAR, customer_id INT, amount DECIMAL, status VARCHAR"
    }
    return schemas.get(table_name, f"Table {table_name} not found")

@tool
def check_pipeline_status(pipeline_name: str) -> str:
    """Check whether a data pipeline ran successfully recently."""
    return f"{pipeline_name}: last run 2024-03-15 02:15 UTC, status=SUCCESS, rows=15234"

tools = [run_sql, get_table_schema, check_pipeline_status]

# ── Build agent ────────────────────────────────────────────────────────────────
llm = ChatAnthropic(model="claude-sonnet-5")

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a data engineering assistant. Use tools to answer accurately."),
    ("human",  "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent          = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=10)

result = agent_executor.invoke({"input": "How many orders do we have and is the pipeline healthy?"})
print(result["output"])
```

---

## LlamaIndex Setup

```bash
pip install llama-index llama-index-llms-anthropic llama-index-llms-openai
pip install llama-index-embeddings-openai llama-index-vector-stores-chroma
```

```python
from llama_index.llms.anthropic import Anthropic
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core import Settings

# Global settings
Settings.llm       = Anthropic(model="claude-sonnet-5")
Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
Settings.chunk_size    = 512
Settings.chunk_overlap = 50
```

---

## LlamaIndex RAG Pipeline

```python
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.core import StorageContext, load_index_from_storage
from llama_index.core.node_parser import SentenceSplitter
from pathlib import Path

# ── Build index from docs directory ───────────────────────────────────────────
documents = SimpleDirectoryReader("./docs/").load_data()

parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)
nodes  = parser.get_nodes_from_documents(documents)

index = VectorStoreIndex(nodes)

# ── Save & load ────────────────────────────────────────────────────────────────
index.storage_context.persist("./storage")

# Load from disk
storage_context = StorageContext.from_defaults(persist_dir="./storage")
index = load_index_from_storage(storage_context)

# ── Query ──────────────────────────────────────────────────────────────────────
query_engine = index.as_query_engine(
    similarity_top_k=5,
    response_mode="compact"   # "compact" | "refine" | "tree_summarize"
)

response = query_engine.query("What is the medallion architecture?")
print(response.response)

# See source nodes
for node in response.source_nodes:
    print(f"Score: {node.score:.3f}  Source: {node.metadata.get('file_name', 'unknown')}")
    print(f"  {node.text[:200]}\n")

# ── Chat mode (multi-turn) ─────────────────────────────────────────────────────
chat_engine = index.as_chat_engine(chat_mode="condense_plus_context")
response = chat_engine.chat("What is Kafka?")
print(response.response)
response = chat_engine.chat("How does it compare to RabbitMQ?")
print(response.response)
```

### With metadata filtering

```python
from llama_index.core.vector_stores import MetadataFilter, MetadataFilters

filters = MetadataFilters(filters=[
    MetadataFilter(key="file_name", value="pyspark-reference.md")
])
query_engine = index.as_query_engine(filters=filters, similarity_top_k=3)
response = query_engine.query("Explain window functions")
```

### Sub-question query engine (multi-document)

```python
from llama_index.core.query_engine import SubQuestionQueryEngine
from llama_index.core.tools import QueryEngineTool

# Build separate indexes per document
pyspark_engine = VectorStoreIndex.from_documents(pyspark_docs).as_query_engine()
airflow_engine = VectorStoreIndex.from_documents(airflow_docs).as_query_engine()

tools = [
    QueryEngineTool.from_defaults(query_engine=pyspark_engine, name="pyspark",
                                   description="PySpark documentation"),
    QueryEngineTool.from_defaults(query_engine=airflow_engine, name="airflow",
                                   description="Airflow documentation"),
]

sub_question_engine = SubQuestionQueryEngine.from_defaults(query_engine_tools=tools)
response = sub_question_engine.query(
    "Compare Spark Structured Streaming with Airflow scheduling for batch workloads"
)
print(response.response)
```

---

## LangChain Expression Language (LCEL)

LCEL uses the `|` operator to compose chains — similar to Unix pipes.

```python
from langchain_core.runnables import RunnableParallel, RunnableLambda

# ── Sequential chain ───────────────────────────────────────────────────────────
chain = prompt | llm | StrOutputParser()

# ── Parallel execution ─────────────────────────────────────────────────────────
parallel_chain = RunnableParallel({
    "summary":    prompt_summary  | llm | StrOutputParser(),
    "key_points": prompt_bullets  | llm | StrOutputParser(),
})
result = parallel_chain.invoke({"text": long_document})

# ── With fallback ──────────────────────────────────────────────────────────────
primary  = ChatAnthropic(model="claude-sonnet-5")
fallback = ChatOpenAI(model="gpt-4o-mini")

chain_with_fallback = (prompt | primary | StrOutputParser()).with_fallbacks(
    [prompt | fallback | StrOutputParser()]
)

# ── Add retry logic ────────────────────────────────────────────────────────────
reliable_llm = llm.with_retry(stop_after_attempt=3, wait_exponential_jitter=True)

# ── Conditional routing ────────────────────────────────────────────────────────
def route(inputs):
    if "sql" in inputs["question"].lower():
        return sql_chain
    elif "pipeline" in inputs["question"].lower():
        return pipeline_chain
    return general_chain

routed_chain = RunnableLambda(route)
```

---

## Custom Retrievers

```python
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

class HybridRetriever(BaseRetriever):
    """Combines vector search and keyword search."""

    vectorstore: object
    bm25_index:  object
    k:           int = 5
    alpha:       float = 0.5  # 0=BM25, 1=vector

    def _get_relevant_documents(self, query: str) -> list[Document]:
        # Vector results
        vec_docs  = self.vectorstore.similarity_search(query, k=self.k * 2)
        # BM25 results
        bm25_docs = self.bm25_index.get_top_n(query.split(), self.k * 2)

        # Reciprocal Rank Fusion
        scores = {}
        for rank, doc in enumerate(vec_docs):
            key = doc.page_content[:50]
            scores[key] = scores.get(key, 0) + self.alpha * (1 / (rank + 1))
        for rank, doc in enumerate(bm25_docs):
            key = doc.page_content[:50]
            scores[key] = scores.get(key, 0) + (1 - self.alpha) * (1 / (rank + 1))

        all_docs = {d.page_content[:50]: d for d in vec_docs + bm25_docs}
        ranked   = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [all_docs[k] for k, _ in ranked[:self.k] if k in all_docs]
```

---

## LangSmith (Tracing & Evals)

LangSmith traces every LLM call — inputs, outputs, latency, cost — for debugging and evaluation.

```bash
pip install langsmith
```

```python
import os
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"]    = "ls__..."
os.environ["LANGCHAIN_PROJECT"]    = "de-bible-rag"

# All LangChain calls are now automatically traced
result = rag_chain.invoke("What is Kafka?")
# Visit https://smith.langchain.com to see the trace
```

```python
# Run evaluations
from langsmith import Client
from langsmith.evaluation import evaluate, LangChainStringEvaluator

client = Client()

# Create a dataset
dataset = client.create_dataset("de-rag-eval")
client.create_examples(
    inputs=[
        {"question": "What is the medallion architecture?"},
        {"question": "How does Kafka guarantee delivery?"},
    ],
    outputs=[
        {"answer": "Bronze/Silver/Gold layers"},
        {"answer": "At-least-once by default, exactly-once with transactions"},
    ],
    dataset_id=dataset.id
)

# Evaluate
results = evaluate(
    lambda inputs: {"output": rag_chain.invoke(inputs["question"])},
    data=dataset.name,
    evaluators=[LangChainStringEvaluator("cot_qa")],
    experiment_prefix="rag-v1"
)
```

---

## When to Use a Framework vs Raw SDK

```
Use the raw SDK when:
  ✓ Simple use case (single LLM call, basic RAG)
  ✓ Production code where you need full control
  ✓ You're optimizing for latency or cost
  ✓ Your team doesn't already know the framework

Use LangChain when:
  ✓ Building complex agent workflows
  ✓ Need to swap LLM providers easily
  ✓ Want built-in streaming, retries, fallbacks
  ✓ Already using LangSmith for tracing

Use LlamaIndex when:
  ✓ Building document Q&A or knowledge base
  ✓ Need advanced retrieval (sub-question, HyDE, re-ranking)
  ✓ Working with large document collections
  ✓ Want higher-level RAG abstractions out of the box
```
