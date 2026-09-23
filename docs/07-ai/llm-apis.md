# LLM APIs & SDKs
> Working with Anthropic Claude and OpenAI APIs — from first call to production patterns.

**Prerequisites:** [Python for DE](../00-foundations/python-reference.md) · [Prompt Engineering](prompt-engineering.md)

**Related:** [AI Agents](ai-agents.md) · [AI Observability](ai-observability.md) · [Glossary](../99-reference/glossary.md)

---

## Table of Contents

**Basic**
- [Overview](#overview)
- [Anthropic SDK Setup](#anthropic-sdk-setup)
- [First API Call](#first-api-call)
- [OpenAI SDK Setup](#openai-sdk-setup)

**Intermediate**
- [Key Parameters](#key-parameters)
- [Streaming](#streaming)
- [Tool Use / Function Calling](#tool-use--function-calling)
- [Vision (Image Input)](#vision-image-input)

**Advanced**
- [Structured Outputs](#structured-outputs)
- [Prompt Caching (Anthropic)](#prompt-caching-anthropic)
- [Batching](#batching)
- [Production Patterns](#production-patterns)

---

## Overview

| | Anthropic | OpenAI |
|-|-----------|--------|
| **Top model** | Claude Opus 5.5 | GPT-4o |
| **Fast model** | Claude Haiku 4.5 | GPT-4o-mini |
| **API style** | Messages API | Chat Completions |
| **Tool use** | Yes | Yes (function calling) |
| **Vision** | Yes | Yes |
| **Structured output** | Via prompt / tool | `response_format: json_object` |
| **Prompt caching** | Yes (explicit) | Yes (automatic) |
| **Python SDK** | `anthropic` | `openai` |

---

## Anthropic SDK Setup

```bash
pip install anthropic
```

```python
import anthropic
import os

# Client reads ANTHROPIC_API_KEY from environment by default
client = anthropic.Anthropic()

# Or explicitly
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
```

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
```

### Model IDs (Claude)

```python
# Current models (as of mid-2025)
CLAUDE_OPUS    = "claude-opus-5-5"        # most capable
CLAUDE_SONNET  = "claude-sonnet-5"         # balanced
CLAUDE_HAIKU   = "claude-haiku-4-5-20251001"  # fastest, cheapest
```

---

## First API Call

```python
import anthropic

client = anthropic.Anthropic()

message = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Explain what a data lakehouse is in 3 bullet points."}
    ]
)

print(message.content[0].text)
```

### With a system prompt

```python
message = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1024,
    system="You are a concise technical writer. Always use bullet points.",
    messages=[
        {"role": "user", "content": "What is Apache Iceberg?"}
    ]
)
```

### Response object

```python
message.id            # unique message ID
message.model         # model used
message.stop_reason   # "end_turn" | "max_tokens" | "stop_sequence" | "tool_use"
message.usage         # Usage(input_tokens=45, output_tokens=210)
message.content       # list of content blocks

# Text response
message.content[0].text
message.content[0].type  # "text"
```

---

## OpenAI SDK Setup

```bash
pip install openai
```

```python
from openai import OpenAI

client = OpenAI()  # reads OPENAI_API_KEY from env

response = client.chat.completions.create(
    model="gpt-4o",
    max_tokens=1024,
    messages=[
        {"role": "system",    "content": "You are a helpful data engineer."},
        {"role": "user",      "content": "What is the difference between a fact and a dimension table?"}
    ]
)

print(response.choices[0].message.content)

# Token usage
response.usage.prompt_tokens
response.usage.completion_tokens
response.usage.total_tokens
```

---

## Key Parameters

| Parameter | Description | Typical values |
|-----------|-------------|----------------|
| `model` | Which model to use | see model IDs above |
| `max_tokens` | Max output tokens | 256–4096 for most tasks |
| `temperature` | Randomness (0=deterministic, 1=creative) | 0 for data tasks, 0.7 for creative |
| `top_p` | Nucleus sampling (alternative to temperature) | 0.9–1.0 |
| `stop_sequences` | Stop generation at these strings | `["\n\n", "END"]` |
| `system` | System prompt (Anthropic) | Instructions, persona, format |

```python
# For data extraction — want determinism
message = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=512,
    temperature=0,           # deterministic
    messages=[{"role": "user", "content": "Extract the table name from: SELECT * FROM orders"}]
)

# For creative content generation — want variation
message = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1024,
    temperature=0.8,
    messages=[{"role": "user", "content": "Write 3 different error message suggestions for a failed pipeline."}]
)
```

---

## Streaming

Stream tokens as they're generated — essential for interactive UIs and long outputs.

```python
# Anthropic streaming
with client.messages.stream(
    model="claude-sonnet-5",
    max_tokens=2048,
    messages=[{"role": "user", "content": "Explain PySpark window functions in detail."}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)

# Get the full message after streaming
message = stream.get_final_message()
print(f"\nTotal tokens: {message.usage.input_tokens + message.usage.output_tokens}")
```

```python
# OpenAI streaming
stream = client.chat.completions.create(
    model="gpt-4o",
    max_tokens=2048,
    stream=True,
    messages=[{"role": "user", "content": "Explain PySpark window functions."}]
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

```python
# Async streaming (for FastAPI / async apps)
import asyncio
import anthropic

async_client = anthropic.AsyncAnthropic()

async def stream_response(prompt: str):
    async with async_client.messages.stream(
        model="claude-sonnet-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    ) as stream:
        async for text in stream.text_stream:
            yield text
```

---

## Tool Use / Function Calling

Let the model call functions you define — the model decides when to call them and with what arguments.

```python
import anthropic
import json

client = anthropic.Anthropic()

# Define tools
tools = [
    {
        "name": "run_sql_query",
        "description": "Execute a SQL query against the data warehouse and return results",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The SQL query to execute"
                },
                "database": {
                    "type": "string",
                    "description": "Target database: 'snowflake' or 'bigquery'",
                    "enum": ["snowflake", "bigquery"]
                }
            },
            "required": ["query", "database"]
        }
    },
    {
        "name": "get_table_schema",
        "description": "Get the schema (column names and types) for a given table",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"}
            },
            "required": ["table_name"]
        }
    }
]

# Simulated tool executor
def execute_tool(name: str, inputs: dict) -> str:
    if name == "run_sql_query":
        return json.dumps({"rows": [{"count": 1523}], "elapsed_ms": 340})
    if name == "get_table_schema":
        return json.dumps({"columns": [
            {"name": "order_id", "type": "VARCHAR"},
            {"name": "amount",   "type": "DECIMAL(10,2)"},
            {"name": "status",   "type": "VARCHAR"},
        ]})
    return "Tool not found"

# Agentic loop
messages = [{"role": "user", "content": "How many orders are in the orders table?"}]

while True:
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        tools=tools,
        messages=messages
    )

    # If model is done, print and exit
    if response.stop_reason == "end_turn":
        for block in response.content:
            if hasattr(block, "text"):
                print(block.text)
        break

    # If model wants to use a tool
    if response.stop_reason == "tool_use":
        # Add assistant's response to messages
        messages.append({"role": "assistant", "content": response.content})

        # Execute each tool call
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })

        # Add tool results to messages
        messages.append({"role": "user", "content": tool_results})
```

---

## Vision (Image Input)

Send images alongside text for analysis, OCR, chart reading, etc.

```python
import anthropic
import base64
from pathlib import Path

client = anthropic.Anthropic()

# Option 1: Base64 encode a local image
image_data = base64.standard_b64encode(Path("pipeline_diagram.png").read_bytes()).decode("utf-8")

message = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1024,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_data,
                    },
                },
                {
                    "type": "text",
                    "text": "Describe this data pipeline diagram. List each component and how they connect."
                }
            ],
        }
    ],
)

# Option 2: Image from URL
message = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1024,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "url",
                        "url": "https://example.com/chart.png"
                    }
                },
                {"type": "text", "text": "What trend does this chart show?"}
            ]
        }
    ]
)
```

---

## Structured Outputs

### Anthropic: tool-based structured output

```python
# Use a tool as a structured output schema — most reliable approach
tools = [{
    "name": "extract_pipeline_metadata",
    "description": "Extract structured metadata from a pipeline description",
    "input_schema": {
        "type": "object",
        "properties": {
            "pipeline_name":  {"type": "string"},
            "schedule":       {"type": "string", "description": "cron expression or plain English"},
            "source_system":  {"type": "string"},
            "destination":    {"type": "string"},
            "is_incremental": {"type": "boolean"},
            "estimated_rows": {"type": "integer"}
        },
        "required": ["pipeline_name", "source_system", "destination"]
    }
}]

response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=512,
    tools=tools,
    tool_choice={"type": "tool", "name": "extract_pipeline_metadata"},  # force this tool
    messages=[{"role": "user", "content": "We have a nightly job that pulls 50k new transactions from Stripe and loads them into Snowflake at 2am."}]
)

# Extract the structured result
for block in response.content:
    if block.type == "tool_use":
        metadata = block.input
        print(metadata)
# {'pipeline_name': 'stripe_transactions_load', 'schedule': '0 2 * * *',
#  'source_system': 'Stripe', 'destination': 'Snowflake',
#  'is_incremental': True, 'estimated_rows': 50000}
```

### OpenAI: json_object mode

```python
from openai import OpenAI
import json

client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o",
    response_format={"type": "json_object"},
    messages=[
        {"role": "system", "content": "Always respond with valid JSON."},
        {"role": "user",   "content": "Extract pipeline name, schedule, and source from: nightly Stripe→Snowflake job at 2am"}
    ]
)

data = json.loads(response.choices[0].message.content)
```

---

## Prompt Caching (Anthropic)

Cache long, repeated content (system prompts, documents) to reduce cost and latency. Cached tokens cost ~10% of regular input tokens.

```python
# Mark content for caching with cache_control: {"type": "ephemeral"}
# Ephemeral cache = 5 minutes TTL (resets on each use)

long_document = Path("data_dictionary.md").read_text()

response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": "You are a data dictionary assistant. Answer questions about the schema.",
        },
        {
            "type": "text",
            "text": long_document,
            "cache_control": {"type": "ephemeral"}  # cache this large document
        }
    ],
    messages=[{"role": "user", "content": "What columns does the orders table have?"}]
)

# Check cache usage
print(response.usage.cache_creation_input_tokens)  # tokens written to cache (first call)
print(response.usage.cache_read_input_tokens)       # tokens read from cache (subsequent calls)
```

**When to cache:**
- Large system prompts (> 1000 tokens)
- Reference documents (data dictionaries, schemas, codebases)
- Few-shot examples at the start of the system prompt
- Multi-turn conversations where the context grows large

---

## Batching

For offline workloads (document processing, bulk classification), use the Batch API — up to 50% cheaper, processed within 24 hours.

```python
# Anthropic Batch API
requests = []
for i, row in enumerate(data):
    requests.append({
        "custom_id": f"row-{i}",
        "params": {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 256,
            "messages": [{"role": "user", "content": f"Classify this log: {row['log']}"}]
        }
    })

batch = client.messages.batches.create(requests=requests)
print(f"Batch ID: {batch.id}, status: {batch.processing_status}")

# Poll for completion
import time
while True:
    batch = client.messages.batches.retrieve(batch.id)
    if batch.processing_status == "ended":
        break
    time.sleep(60)

# Retrieve results
for result in client.messages.batches.results(batch.id):
    print(result.custom_id, result.result.message.content[0].text)
```

---

## Production Patterns

### Retry with exponential backoff

```python
import time
import anthropic
from anthropic import RateLimitError, APIStatusError

def call_with_retry(client, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return client.messages.create(**kwargs)
        except RateLimitError:
            wait = 2 ** attempt
            print(f"Rate limited. Waiting {wait}s...")
            time.sleep(wait)
        except APIStatusError as e:
            if e.status_code >= 500:  # server error — retry
                time.sleep(2 ** attempt)
            else:
                raise  # client error — don't retry
    raise RuntimeError("Max retries exceeded")
```

### Cost tracking

```python
# Approximate cost calculation (check current pricing)
PRICING = {
    "claude-sonnet-5":          {"input": 3.00,  "output": 15.00},   # per 1M tokens
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00},
    "claude-opus-5-5":           {"input": 15.00, "output": 75.00},
}

def estimate_cost(response) -> float:
    model = response.model
    if model not in PRICING:
        return 0.0
    p = PRICING[model]
    input_cost  = response.usage.input_tokens  / 1_000_000 * p["input"]
    output_cost = response.usage.output_tokens / 1_000_000 * p["output"]
    return input_cost + output_cost

response = client.messages.create(...)
print(f"Cost: ${estimate_cost(response):.6f}")
```

### Async for concurrent calls

```python
import asyncio
import anthropic

async_client = anthropic.AsyncAnthropic()

async def classify(text: str, idx: int) -> dict:
    response = await async_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=64,
        temperature=0,
        messages=[{"role": "user", "content": f"Classify as PASS or FAIL: {text}"}]
    )
    return {"idx": idx, "result": response.content[0].text.strip()}

async def classify_all(texts: list[str]) -> list[dict]:
    tasks = [classify(text, i) for i, text in enumerate(texts)]
    return await asyncio.gather(*tasks)

results = asyncio.run(classify_all(["Row count > 0", "NULL in required field", "Schema matches expected"]))
```

### Logging all LLM calls

```python
import logging
import uuid
from functools import wraps

logger = logging.getLogger("llm_calls")

def log_llm_call(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        call_id = str(uuid.uuid4())[:8]
        logger.info(f"[{call_id}] LLM call | model={kwargs.get('model')} | "
                    f"prompt_preview={str(kwargs.get('messages',''))[:100]}")
        response = func(*args, **kwargs)
        logger.info(f"[{call_id}] LLM done | tokens={response.usage.input_tokens}+{response.usage.output_tokens} | "
                    f"stop={response.stop_reason}")
        return response
    return wrapper

@log_llm_call
def create_message(client, **kwargs):
    return client.messages.create(**kwargs)
```

---

**Previous:** [Prompt Engineering](prompt-engineering.md) · **Next:** [Embeddings](embeddings.md) · **Back to:** [Index](../README.md)
