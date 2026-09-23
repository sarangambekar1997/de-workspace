# AI Agents & Tool Use
> Building LLM systems that take actions, use tools, and complete multi-step tasks autonomously.

**Prerequisites:** [LLM APIs](llm-apis.md) · [Prompt Engineering](prompt-engineering.md)

**Related:** [LangChain & LlamaIndex](langchain-llamaindex.md) · [Claude Code](claude-code.md) · [Evals](eval-and-evals.md) · [Glossary](../99-reference/glossary.md)

---

## Table of Contents

**Basic**
- [What Is an AI Agent](#what-is-an-ai-agent)
- [Tool Use Fundamentals](#tool-use-fundamentals)
- [Single-Step Tool Use](#single-step-tool-use)

**Intermediate**
- [Agentic Loop](#agentic-loop)
- [Building a DE Agent](#building-a-de-agent)
- [ReAct Pattern](#react-pattern)
- [Error Handling in Agents](#error-handling-in-agents)

**Advanced**
- [Multi-Agent Systems](#multi-agent-systems)
- [Agent Memory](#agent-memory)
- [Human-in-the-Loop](#human-in-the-loop)
- [Production Agent Patterns](#production-agent-patterns)

---

## What Is an AI Agent

An agent is an LLM that can take actions — it calls tools, observes results, and decides what to do next, repeating until it completes the task.

```
Chatbot:  User asks → LLM responds (one step)
Agent:    User asks → LLM thinks → calls tool → observes result
                   → LLM thinks → calls tool → observes result
                   → LLM thinks → answers (many steps)
```

**Key components:**

| Component | Role |
|-----------|------|
| **LLM** | The brain — decides what action to take next |
| **Tools** | Functions the LLM can call (search, SQL, API calls, file ops) |
| **Memory** | Context from previous steps and conversations |
| **Planner** | (optional) Breaks big tasks into subtasks |
| **Executor** | Runs the tool calls and returns results |

---

## Tool Use Fundamentals

The LLM doesn't directly execute code — it generates a structured "call this function with these arguments" request. Your code executes it and returns the result.

```
LLM output:  {"tool": "run_sql", "args": {"query": "SELECT COUNT(*) FROM orders"}}
Your code:   runs the query → returns {"count": 15234}
LLM input:   "The query returned 15234 rows"
LLM output:  "There are 15,234 orders in the table."
```

**Tool definition (Anthropic):**

```python
tool = {
    "name": "run_sql",
    "description": "Execute a SQL query and return results. Use for counting, aggregating, or looking up data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "SQL query to execute. Must be a SELECT statement."
            },
            "limit": {
                "type": "integer",
                "description": "Max rows to return (default 100)",
                "default": 100
            }
        },
        "required": ["query"]
    }
}
```

**What makes a good tool:**
1. **Clear description** — the LLM uses this to decide when to call it
2. **Narrow scope** — one tool does one thing
3. **Safe by default** — read-only where possible; destructive actions need confirmation
4. **Handles errors gracefully** — return error as a string, not an exception

---

## Single-Step Tool Use

```python
import anthropic
import json

client = anthropic.Anthropic()

tools = [
    {
        "name": "get_table_row_count",
        "description": "Get the number of rows in a database table",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "Name of the table"}
            },
            "required": ["table_name"]
        }
    }
]

def get_table_row_count(table_name: str) -> dict:
    # Simulated — in production, this runs a real query
    counts = {"orders": 152340, "customers": 48921, "products": 5420}
    if table_name in counts:
        return {"table": table_name, "row_count": counts[table_name]}
    return {"error": f"Table '{table_name}' not found"}

# First turn: LLM decides to use the tool
response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "How many orders do we have?"}]
)

# Extract tool call
for block in response.content:
    if block.type == "tool_use":
        print(f"Tool: {block.name}, Args: {block.input}")
        result = get_table_row_count(**block.input)
        print(f"Result: {result}")

        # Second turn: give result back to LLM
        final = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=512,
            tools=tools,
            messages=[
                {"role": "user",      "content": "How many orders do we have?"},
                {"role": "assistant", "content": response.content},
                {"role": "user",      "content": [{"type": "tool_result",
                                                    "tool_use_id": block.id,
                                                    "content": json.dumps(result)}]}
            ]
        )
        print(final.content[0].text)
        # "We currently have 152,340 orders in the database."
```

---

## Agentic Loop

A loop that continues until the model stops calling tools.

```python
import anthropic
import json

client = anthropic.Anthropic()

def run_agent(user_message: str, tools: list, tool_executor: dict,
              system: str = "", max_iterations: int = 10) -> str:
    """
    Generic agentic loop.
    tool_executor: {"tool_name": callable}
    """
    messages = [{"role": "user", "content": user_message}]

    for i in range(max_iterations):
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=4096,
            system=system,
            tools=tools,
            messages=messages
        )

        # Agent is done
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return ""

        # Agent wants to use tools
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                print(f"[Tool call] {block.name}({json.dumps(block.input)})")

                if block.name in tool_executor:
                    try:
                        result = tool_executor[block.name](**block.input)
                        result_str = json.dumps(result) if isinstance(result, dict) else str(result)
                        print(f"[Tool result] {result_str[:200]}")
                    except Exception as e:
                        result_str = f"ERROR: {str(e)}"
                        print(f"[Tool error] {result_str}")
                else:
                    result_str = f"ERROR: Tool '{block.name}' not available"

                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     result_str
                })

            messages.append({"role": "user", "content": tool_results})

    return "Max iterations reached without completing the task."
```

---

## Building a DE Agent

A practical data engineering agent that can query schemas, run SQL, and check pipeline status.

```python
import anthropic
import json
from datetime import datetime

client = anthropic.Anthropic()

# ── Tool definitions ──────────────────────────────────────────────────────────
DE_TOOLS = [
    {
        "name": "list_tables",
        "description": "List all available tables in the data warehouse",
        "input_schema": {
            "type": "object",
            "properties": {
                "schema": {"type": "string", "description": "Schema/database name (optional)"}
            }
        }
    },
    {
        "name": "get_table_schema",
        "description": "Get column names and types for a specific table",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"}
            },
            "required": ["table_name"]
        }
    },
    {
        "name": "run_sql",
        "description": "Execute a read-only SQL query. Use for counts, aggregations, sampling data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Must be a SELECT statement"},
                "limit": {"type": "integer", "default": 20}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_pipeline_status",
        "description": "Get the recent run status of a data pipeline",
        "input_schema": {
            "type": "object",
            "properties": {
                "pipeline_name": {"type": "string"}
            },
            "required": ["pipeline_name"]
        }
    },
    {
        "name": "check_data_freshness",
        "description": "Check how recent the data is in a table",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "timestamp_column": {"type": "string", "default": "updated_at"}
            },
            "required": ["table_name"]
        }
    }
]

# ── Tool implementations (simulated) ──────────────────────────────────────────
def list_tables(schema=None):
    return {"tables": ["orders", "customers", "products", "dim_date", "fct_revenue"]}

def get_table_schema(table_name):
    schemas = {
        "orders": [
            {"column": "order_id",    "type": "VARCHAR",        "nullable": False},
            {"column": "customer_id", "type": "INTEGER",        "nullable": False},
            {"column": "amount",      "type": "DECIMAL(10,2)",  "nullable": False},
            {"column": "status",      "type": "VARCHAR",        "nullable": False},
            {"column": "created_at",  "type": "TIMESTAMP",      "nullable": False},
        ]
    }
    return schemas.get(table_name, {"error": f"Table {table_name} not found"})

def run_sql(query, limit=20):
    # Safety check — only allow SELECT
    if not query.strip().upper().startswith("SELECT"):
        return {"error": "Only SELECT statements are allowed"}
    # Simulated results
    return {"rows": [{"count": 152340}], "columns": ["count"], "elapsed_ms": 87}

def get_pipeline_status(pipeline_name):
    return {
        "pipeline": pipeline_name,
        "last_run": "2024-03-15 02:15:43",
        "status":   "success",
        "duration_minutes": 23,
        "rows_processed": 15234
    }

def check_data_freshness(table_name, timestamp_column="updated_at"):
    return {
        "table":          table_name,
        "latest_record":  "2024-03-15 02:08:31",
        "hours_old":      0.5,
        "sla_hours":      2,
        "status":         "FRESH"
    }

TOOL_MAP = {
    "list_tables":          list_tables,
    "get_table_schema":     get_table_schema,
    "run_sql":              run_sql,
    "get_pipeline_status":  get_pipeline_status,
    "check_data_freshness": check_data_freshness,
}

SYSTEM = """You are a data engineering assistant with access to the data warehouse.
Use the provided tools to answer questions accurately.
Always check the actual data rather than guessing.
Format numbers with commas. Be concise."""

# ── Run the agent ─────────────────────────────────────────────────────────────
answer = run_agent(
    user_message="Is the orders data up to date? And how many orders came in today?",
    tools=DE_TOOLS,
    tool_executor=TOOL_MAP,
    system=SYSTEM
)
print(answer)
```

---

## ReAct Pattern

**Reason + Act** — the model alternates between thinking and acting. Makes reasoning transparent and easier to debug.

```python
# ReAct via chain-of-thought in the system prompt
REACT_SYSTEM = """You are an analytical assistant. Think through problems step by step.

When solving a task, use this format:
Thought: What do I know? What do I need to find out?
Action: Which tool to call and why
Observation: What the tool returned
... (repeat until you have enough information)
Thought: I now have everything I need
Answer: Final answer to the user

Always show your reasoning before calling tools."""

# The model will naturally produce:
# Thought: The user wants to know if orders data is fresh. I should check the freshness.
# Action: check_data_freshness(table_name="orders")
# Observation: {"hours_old": 0.5, "status": "FRESH"}
# Thought: Data is fresh. Now I need today's order count.
# Action: run_sql(query="SELECT COUNT(*) FROM orders WHERE DATE(created_at) = CURRENT_DATE")
# Observation: {"rows": [{"count": 8423}]}
# Answer: The orders data is fresh (last updated 30 minutes ago). Today we've received 8,423 orders.
```

---

## Error Handling in Agents

```python
def safe_tool_call(tool_fn, **kwargs) -> str:
    """Wrap every tool call — return errors as strings so the agent can recover."""
    try:
        result = tool_fn(**kwargs)
        return json.dumps(result)
    except PermissionError as e:
        return json.dumps({"error": "permission_denied", "detail": str(e)})
    except TimeoutError:
        return json.dumps({"error": "timeout", "detail": "Query timed out after 30s. Try a more specific query."})
    except Exception as e:
        return json.dumps({"error": "tool_failed", "detail": str(e)})

# Agents can recover from errors — give them the error message as context
# Example:
# Tool result: {"error": "timeout", "detail": "Query timed out after 30s"}
# Agent: "I see the query timed out. Let me try with a date filter to reduce the data scanned."
# Next action: run_sql(query="SELECT COUNT(*) FROM orders WHERE created_at >= CURRENT_DATE")
```

---

## Multi-Agent Systems

Multiple specialized agents working together.

```python
# Orchestrator → Subagents pattern
# Orchestrator decides which specialist to call; specialists do the work

ORCHESTRATOR_TOOLS = [
    {
        "name": "call_data_agent",
        "description": "Call the data agent to query the warehouse or check schemas",
        "input_schema": {
            "type": "object",
            "properties": {"task": {"type": "string"}},
            "required": ["task"]
        }
    },
    {
        "name": "call_pipeline_agent",
        "description": "Call the pipeline agent to check DAG status or pipeline health",
        "input_schema": {
            "type": "object",
            "properties": {"task": {"type": "string"}},
            "required": ["task"]
        }
    }
]

def call_data_agent(task: str) -> str:
    return run_agent(task, tools=DE_TOOLS, tool_executor=TOOL_MAP,
                     system="You are a data warehouse expert.")

def call_pipeline_agent(task: str) -> str:
    # Different system prompt, different tools focused on pipelines
    return run_agent(task, tools=DE_TOOLS, tool_executor=TOOL_MAP,
                     system="You are a pipeline reliability engineer.")

orchestrator_result = run_agent(
    user_message="Give me a morning report: data freshness for all key tables and pipeline status.",
    tools=ORCHESTRATOR_TOOLS,
    tool_executor={
        "call_data_agent":     call_data_agent,
        "call_pipeline_agent": call_pipeline_agent,
    },
    system="You are an orchestrator. Delegate tasks to specialist agents."
)
```

---

## Agent Memory

Agents are stateless by default — each call starts fresh. Add memory explicitly.

```python
from collections import deque

class AgentWithMemory:
    def __init__(self, tools, tool_executor, system, max_history=20):
        self.tools         = tools
        self.tool_executor = tool_executor
        self.system        = system
        self.history       = deque(maxlen=max_history)  # rolling window

    def chat(self, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})
        messages = list(self.history)

        # Run agent with full history
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=2048,
            system=self.system,
            tools=self.tools,
            messages=messages
        )

        # Handle tool use
        if response.stop_reason == "tool_use":
            # ... (same agentic loop logic)
            pass

        # Save response to history
        answer = response.content[0].text
        self.history.append({"role": "assistant", "content": answer})
        return answer

agent = AgentWithMemory(tools=DE_TOOLS, tool_executor=TOOL_MAP,
                        system=SYSTEM)

print(agent.chat("How many orders do we have?"))
print(agent.chat("And how many of those are from today?"))  # remembers previous context
print(agent.chat("What's the average order value?"))
```

---

## Human-in-the-Loop

For destructive or high-stakes actions, require human approval before execution.

```python
DESTRUCTIVE_TOOLS = {"delete_table", "truncate_table", "run_write_sql", "deploy_pipeline"}

def tool_executor_with_approval(tool_name: str, tool_fn, **kwargs) -> str:
    if tool_name in DESTRUCTIVE_TOOLS:
        print(f"\n⚠️  Agent wants to call: {tool_name}")
        print(f"   Arguments: {json.dumps(kwargs, indent=2)}")
        confirm = input("   Approve? (yes/no): ").strip().lower()
        if confirm != "yes":
            return json.dumps({"status": "cancelled", "reason": "User did not approve this action"})

    return safe_tool_call(tool_fn, **kwargs)
```

---

## Production Agent Patterns

### Timeout and cost guard

```python
import time

class AgentGuard:
    def __init__(self, max_tokens: int = 50_000, max_seconds: int = 120):
        self.max_tokens  = max_tokens
        self.max_seconds = max_seconds
        self.total_tokens = 0
        self.start_time   = time.time()

    def check(self, response):
        self.total_tokens += response.usage.input_tokens + response.usage.output_tokens
        if self.total_tokens > self.max_tokens:
            raise RuntimeError(f"Token budget exceeded: {self.total_tokens} > {self.max_tokens}")
        if time.time() - self.start_time > self.max_seconds:
            raise RuntimeError(f"Time budget exceeded: {self.max_seconds}s")
```

### Structured output at the end

```python
FINAL_ANSWER_TOOL = {
    "name": "final_answer",
    "description": "Call this when you have a complete answer. Use it to return structured results.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary":     {"type": "string"},
            "data":        {"type": "object"},
            "confidence":  {"type": "string", "enum": ["high", "medium", "low"]},
            "caveats":     {"type": "array", "items": {"type": "string"}}
        },
        "required": ["summary"]
    }
}
# Force a structured output even from a free-form agent
# The agent uses its tools then calls final_answer with the structured result
```

---

**Previous:** [Vector Databases](vector-databases.md) · **Next:** [LangChain & LlamaIndex](langchain-llamaindex.md) · **Back to:** [Index](../README.md)
