# Claude Code
> Anthropic's official CLI and agentic coding tool — from first command to advanced workflows.

**Prerequisites:** [Git for DE](../00-foundations/git-for-de.md) · [Linux & Bash](../00-foundations/linux-bash.md)

**Related:** [AI Agents](ai-agents.md) · [LLM APIs](llm-apis.md) · [Glossary](../99-reference/glossary.md)

---

## Table of Contents

**Basic**
- [What Is Claude Code](#what-is-claude-code)
- [Installation & Setup](#installation--setup)
- [First Session](#first-session)
- [Core Commands](#core-commands)

**Intermediate**
- [Working with Code](#working-with-code)
- [Memory System](#memory-system)
- [CLAUDE.md Files](#claudemd-files)
- [MCP Servers](#mcp-servers)

**Advanced**
- [Hooks](#hooks)
- [Custom Slash Commands (Skills)](#custom-slash-commands-skills)
- [Headless & CI Mode](#headless--ci-mode)
- [DE-Specific Workflows](#de-specific-workflows)

---

## What Is Claude Code

Claude Code is a terminal-based agentic coding tool. It runs in your shell, reads your codebase, and can edit files, run commands, search, and complete multi-step engineering tasks.

```
Traditional AI assistant:    You copy-paste code, apply manually, iterate
Claude Code:                 Claude reads your repo, edits files directly,
                             runs tests, fixes errors, commits — you review
```

**What it can do:**
- Read and edit files across your entire codebase
- Run shell commands (tests, linters, build tools)
- Search for symbols, patterns, and files
- Understand context from git history, tests, and docs
- Remember project-specific rules via CLAUDE.md
- Extend with MCP servers (external tools, databases, APIs)

---

## Installation & Setup

```bash
# Install (requires Node.js 18+)
npm install -g @anthropic-ai/claude-code

# Verify
claude --version

# Authenticate (opens browser for OAuth)
claude

# Or use an API key directly
export ANTHROPIC_API_KEY=sk-ant-...
claude
```

```bash
# In VS Code — install the extension from the marketplace
# Search: "Claude Code" by Anthropic

# JetBrains (IntelliJ, PyCharm, etc.)
# Plugins → Marketplace → search "Claude Code"
```

---

## First Session

```bash
# Start an interactive session in your project directory
cd my-project
claude

# You're now in an interactive session
# Type your task in natural language:

> Explain what this codebase does
> Find all places where we read from S3
> Add error handling to the load_data function in pipeline.py
> Run the tests and fix any failures
> Create a new Airflow DAG that runs daily at 2am
```

```bash
# Quick one-off question (no interactive session)
claude "What does the run_pipeline function do?"

# One-off with output to stdout (useful in scripts)
claude --print "List all Python files that import pandas"
```

---

## Core Commands

```bash
# In-session slash commands
/help                    # show available commands
/clear                   # clear conversation context
/compact                 # summarize context to save tokens
/cost                    # show token usage and cost for this session
/status                  # show current model, context, settings

# Model selection
/model claude-sonnet-5   # switch model mid-session
/fast                    # toggle fast mode (Opus with faster output)

# Memory
/memory                  # view and edit memory files

# Code review
/code-review             # run a code review on current branch changes
/code-review ultra       # multi-agent cloud review (billed)

# Init
/init                    # create a CLAUDE.md for this project
```

---

## Working with Code

Claude Code reads files before editing them — it always has full context.

```bash
# Tell it what to do naturally:
> Fix the bug in pipeline/loader.py where it crashes on empty DataFrames

> Refactor the extract_orders function to use chunked processing
  so it doesn't OOM on large files

> Add logging to every function in the transforms/ directory

> The dbt model fct_orders.sql is too slow — optimize it

> Write tests for the S3Loader class in tests/test_loader.py

> The CI is failing on the type check step — fix all mypy errors
```

**Permission modes:**

| Mode | What auto-approves |
|------|--------------------|
| **Default** | File reads; prompts for file edits, shell commands |
| **Auto-approve** | File reads and edits; prompts for shell commands |
| `--dangerously-skip-permissions` | Everything (use only in trusted CI environments) |

```bash
# Run with auto-approve for edits (still prompts for destructive shell commands)
claude --approve-tools "Edit,Write,Read"
```

---

## Memory System

Claude Code persists memory across sessions in `~/.claude/projects/<project>/memory/`.

```bash
# Explicitly ask Claude to remember something
> Remember that we always use snake_case for dbt model names

> Remember that the Snowflake dev environment credentials
  are in 1Password under "Snowflake Dev"

> Remember that we run dbt tests with --fail-fast in CI

# Claude will save these as memory files and load them in future sessions
```

**Memory types:**
- `user/` — your role, preferences, expertise
- `feedback/` — corrections and confirmed approaches
- `project/` — current project context, decisions, deadlines
- `reference/` — where to find external information

---

## CLAUDE.md Files

`CLAUDE.md` is a project-level instruction file that Claude always reads. Commit it to your repo.

```markdown
# CLAUDE.md — project-level instructions for Claude Code

## Project overview
This is a data engineering monorepo with Airflow DAGs, dbt models, and PySpark jobs.
The data stack: Snowflake + dbt + Airflow on EKS + Databricks for Spark jobs.

## Code conventions
- Python: ruff for linting, black for formatting, mypy for types
- dbt models: snake_case, prefix staging models with stg_, marts with fct_ or dim_
- SQL: uppercase keywords, 4-space indentation, one column per line in SELECT
- Airflow: TaskFlow API for new DAGs; legacy DAGs use PythonOperator

## Running things
- Tests: `pytest tests/ -v`
- dbt: `dbt build --select state:modified+` (from /dbt directory)
- Linting: `ruff check . && mypy .`
- Airflow: `docker compose up -d` (local dev environment)

## Important files
- Pipeline configs: config/pipelines.yaml
- Snowflake connections: .env.example (never commit .env)
- dbt profiles: ~/.dbt/profiles.yml (not in repo)

## What NOT to do
- Never commit credentials — use environment variables
- Never run dbt in production without --defer --state
- Never drop tables directly — always use dbt snapshots or incremental models
- Don't use SELECT * in production dbt models
```

```bash
# CLAUDE.md can be at multiple levels:
~/.claude/CLAUDE.md                  # global (applies everywhere)
~/projects/de-workspace/CLAUDE.md    # repo root
~/projects/de-workspace/dbt/CLAUDE.md  # subdirectory (only when in that dir)
```

---

## MCP Servers

MCP (Model Context Protocol) extends Claude Code with external tools — databases, APIs, services.

```bash
# Add an MCP server (globally)
claude mcp add my-server npx -y @my-org/my-mcp-server

# Add with environment variables
claude mcp add snowflake-server npx -y @org/snowflake-mcp \
  -e SNOWFLAKE_ACCOUNT=myaccount \
  -e SNOWFLAKE_USER=myuser \
  -e SNOWFLAKE_PASSWORD=mypassword

# List configured MCP servers
claude mcp list

# Remove
claude mcp remove my-server
```

```json
// .claude/mcp_servers.json — project-level MCP config (commit to repo)
{
  "mcpServers": {
    "snowflake": {
      "command": "npx",
      "args": ["-y", "@org/snowflake-mcp"],
      "env": {
        "SNOWFLAKE_ACCOUNT": "${SNOWFLAKE_ACCOUNT}",
        "SNOWFLAKE_USER":    "${SNOWFLAKE_USER}"
      }
    },
    "airflow": {
      "command": "python",
      "args": ["-m", "airflow_mcp_server"],
      "env": {
        "AIRFLOW_URL":   "http://localhost:8080",
        "AIRFLOW_TOKEN": "${AIRFLOW_API_TOKEN}"
      }
    }
  }
}
```

With an MCP server, Claude can:
```
> How many orders came in today?   → (queries Snowflake directly)
> Is the daily_orders DAG healthy? → (checks Airflow API)
> What's in the bronze layer?      → (browses S3 via filesystem MCP)
```

---

## Hooks

Hooks run shell commands automatically when Claude Code takes certain actions — for enforcing standards, running checks, or integrating with external systems.

```json
// ~/.claude/settings.json (or .claude/settings.json for project-level)
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "ruff check $CLAUDE_FILE_PATH --fix 2>&1 || true"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "echo \"[Hook] Shell command: $CLAUDE_BASH_COMMAND\""
          }
        ]
      }
    ]
  }
}
```

**Hook event types:**

| Event | Triggers when |
|-------|--------------|
| `PreToolUse` | Before Claude calls a tool |
| `PostToolUse` | After Claude calls a tool |
| `Notification` | Claude sends a notification |
| `Stop` | Claude finishes a turn |

```json
// Useful hook patterns

// Auto-format Python after every file edit
{
  "matcher": "Edit",
  "hooks": [{
    "type": "command",
    "command": "black $CLAUDE_FILE_PATH 2>/dev/null || true"
  }]
}

// Run dbt compile after every SQL model edit
{
  "matcher": "Edit",
  "hooks": [{
    "type": "command",
    "command": "if [[ $CLAUDE_FILE_PATH == *.sql ]]; then cd dbt && dbt compile --quiet; fi"
  }]
}

// Notify on completion (macOS)
{
  "event": "Stop",
  "hooks": [{
    "type": "command",
    "command": "osascript -e 'display notification \"Claude Code finished\" with title \"Claude Code\"'"
  }]
}
```

---

## Custom Slash Commands (Skills)

Create project-specific slash commands in `.claude/agents/`.

```markdown
<!-- .claude/agents/dbt-review.md -->
---
name: dbt-review
description: Review a dbt model for best practices
---

When invoked with /dbt-review:

1. Read the SQL file passed as argument (or the most recently edited .sql file)
2. Check for:
   - Missing ref() usage (hardcoded table names)
   - SELECT * usage
   - Missing tests in schema.yml
   - Missing documentation in schema.yml
   - Performance issues (cross joins, missing WHERE on large tables)
   - Incorrect materialization for the model's usage pattern
3. Report findings as a prioritized list: HIGH / MEDIUM / LOW
4. Suggest the specific fix for each finding
```

```markdown
<!-- .claude/agents/pipeline-debug.md -->
---
name: pipeline-debug
description: Debug a failing Airflow DAG
---

When invoked with /pipeline-debug <dag_name>:

1. Check the Airflow logs for the most recent failed run
2. Identify the failing task and the error message
3. Read the DAG file and the operator implementation
4. Diagnose the root cause
5. Propose a fix with code changes
```

```bash
# Use in a session:
> /dbt-review models/marts/fct_orders.sql
> /pipeline-debug daily_orders
```

---

## Headless & CI Mode

Run Claude Code non-interactively in scripts and CI pipelines.

```bash
# Single command, print output, exit
claude --print "Review the changes in this PR for data quality issues" \
  --dangerously-skip-permissions

# In a CI pipeline (GitHub Actions)
```

```yaml
# .github/workflows/claude-review.yml
name: Claude Code Review

on:
  pull_request:
    paths: ['dbt/**', 'pipelines/**']

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history for git diff

      - name: Install Claude Code
        run: npm install -g @anthropic-ai/claude-code

      - name: Run Claude review
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          claude --print \
            "Review the dbt model changes in this PR. Check for: missing tests, \
             SELECT *, hardcoded table names, performance issues. \
             Output a markdown summary." \
            --dangerously-skip-permissions \
            > review.md

      - name: Post review as PR comment
        uses: marocchino/sticky-pull-request-comment@v2
        with:
          path: review.md
```

---

## DE-Specific Workflows

### Generate dbt model from source table

```
> Look at the raw orders table schema in Snowflake (use the snowflake MCP tool)
  and generate a staging model stg_stripe__orders that:
  - Renames columns to snake_case
  - Casts created_at to timestamp_ntz
  - Adds a dbt_updated_at column
  - Adds source() reference and schema.yml with not_null and unique tests
```

### Debug a failing pipeline

```
> The daily_orders Airflow DAG has been failing since yesterday.
  Check the logs, find the error, trace it to the root cause,
  and propose a fix. Don't make changes yet — just diagnose.
```

### Optimize a slow dbt model

```
> The fct_revenue_by_region model takes 45 minutes in production.
  Read the model, identify the bottleneck, and rewrite it to run
  under 5 minutes. Add an explanation of what changed and why.
```

### Write tests for existing pipelines

```
> Look at all the Airflow DAGs in dags/ that don't have corresponding
  tests in tests/dags/. Write pytest tests for each one covering:
  - DAG imports without errors
  - Task dependency structure
  - Schedule interval correctness
  - Required connections and variables are present
```

### Document a codebase

```
> Read all the Python files in pipelines/ and generate a PIPELINES.md
  that documents: what each pipeline does, its schedule, its inputs
  and outputs, and any known limitations or TODOs.
```

### Migrate code

```
> Convert all the Airflow DAGs in dags/ that use PythonOperator
  and task dependencies with >> to use the TaskFlow API (@task decorator).
  Keep the same logic and schedules. Run the tests after each migration.
```

---

**Previous:** [MLflow](mlflow.md) · **Next:** [Fine-Tuning](fine-tuning.md) · **Back to:** [Index](../README.md)
