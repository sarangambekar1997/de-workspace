# Git for Data Engineers
> Version control workflows tailored to data pipelines, dbt projects, and team collaboration.

---

## Table of Contents

**Basics**
- [Core Concepts](#core-concepts)
- [Essential Commands](#essential-commands)
- [Staging & Committing](#staging--committing)
- [Branching](#branching)

**Intermediate**
- [Remote Repositories](#remote-repositories)
- [Merging & Rebasing](#merging--rebasing)
- [Undoing Changes](#undoing-changes)
- [.gitignore for DE Projects](#gitignore-for-de-projects)

**Advanced**
- [Git Workflow for Data Teams](#git-workflow-for-data-teams)
- [Git for dbt Projects](#git-for-dbt-projects)
- [Git Hooks in Pipelines](#git-hooks-in-pipelines)
- [Useful Aliases & Tips](#useful-aliases--tips)

---

## Core Concepts

| Concept | Definition |
|---------|-----------|
| **Repository** | A directory tracked by Git; contains the full history of all changes |
| **Working tree** | Your local files as they are right now |
| **Staging area** | Files marked to include in the next commit (`git add`) |
| **Commit** | A snapshot of staged changes with a message, timestamp, and author |
| **Branch** | A lightweight pointer to a commit; branches diverge and merge |
| **HEAD** | Pointer to the current commit (usually the tip of the current branch) |
| **Remote** | A copy of the repo hosted elsewhere (GitHub, GitLab, Bitbucket, Azure DevOps) |
| **origin** | Default name for the primary remote |
| **Clone** | A full local copy of a remote repo |
| **Fork** | A personal copy of someone else's repo (GitHub concept) |

```
Working tree → (git add) → Staging area → (git commit) → Local repo → (git push) → Remote
                                                                ↑
                                                    (git pull / git fetch + merge)
```

---

## Essential Commands

```bash
# ── Setup ─────────────────────────────────────────
git config --global user.name "Alice Smith"
git config --global user.email "[REDACTED_EMAIL_ADDRESS_9]"
git config --global core.editor "vim"
git config --list                          # view all config

# ── Init / Clone ──────────────────────────────────
git init                                   # init new repo in current directory
git clone https://github.com/org/repo.git  # clone a remote repo
git clone https://github.com/org/repo.git my-dir  # clone into specific folder

# ── Status & Inspection ───────────────────────────
git status                                 # what's changed / staged / untracked
git diff                                   # unstaged changes
git diff --staged                          # staged changes (about to be committed)
git log                                    # commit history
git log --oneline                          # compact one-line log
git log --oneline --graph --all            # visual branch tree
git log --author="Alice" --since="1 week ago"
git show abc1234                           # show a specific commit
git blame models/fct_orders.sql            # who changed each line
```

---

## Staging & Committing

```bash
# Stage files
git add file.py                    # stage a specific file
git add models/                    # stage an entire directory
git add *.sql                      # stage all SQL files
git add -p                         # interactive staging — pick specific hunks

# Commit
git commit -m "feat: add incremental load to fct_orders"
git commit                         # opens editor for longer message

# Stage + commit in one step (only for tracked files)
git commit -am "fix: correct NULL handling in stg_orders"

# Amend last commit (before pushing)
git commit --amend -m "new message"     # change message
git commit --amend --no-edit            # add more staged changes to last commit
```

### Good commit messages

```
# Format: <type>: <short summary in imperative mood>
# Body explains WHY, not WHAT (the diff shows what)

feat: add incremental load strategy to fct_orders
fix: handle NULL customer_id in stg_orders join
refactor: extract clean_phone_number into a macro
test: add unique and not_null tests to dim_customer
docs: document bronze-silver-gold naming convention
chore: update dbt-core to 1.7.0

# Types: feat, fix, refactor, test, docs, chore, perf, ci
```

---

## Branching

```bash
# Create and switch
git branch feature/incremental-orders      # create branch
git checkout feature/incremental-orders    # switch to it
git checkout -b feature/incremental-orders # create + switch in one step
git switch -c feature/incremental-orders   # modern syntax (Git 2.23+)

# List branches
git branch                       # local branches
git branch -r                    # remote branches
git branch -a                    # all branches

# Delete
git branch -d feature/done       # delete (safe — won't delete if unmerged)
git branch -D feature/abandon    # force delete
git push origin --delete feature/old-branch  # delete remote branch

# Rename current branch
git branch -m new-name
```

### Branch naming conventions

```
main / master        — production-ready code
develop              — integration branch (some teams)

feature/<ticket>-<description>   # feature/DE-123-add-orders-pipeline
fix/<ticket>-<description>        # fix/DE-456-null-handling
hotfix/<description>              # hotfix/critical-prod-fix
release/<version>                 # release/v1.2.0
```

---

## Remote Repositories

```bash
# Remotes
git remote -v                              # list remotes
git remote add origin https://github.com/org/repo.git
git remote set-url origin <new-url>        # change remote URL

# Fetch vs Pull
git fetch origin                           # download remote changes, don't merge
git fetch --all                            # fetch all remotes
git pull                                   # fetch + merge (or rebase if configured)
git pull origin main                       # pull specific branch

# Push
git push origin feature/my-branch         # push branch to remote
git push -u origin feature/my-branch      # push + set upstream (then just git push)
git push                                   # push current branch to upstream
git push --force-with-lease               # safer force push (fails if remote changed)

# Tracking remote branches
git checkout --track origin/feature/remote-branch  # track + checkout remote branch
```

---

## Merging & Rebasing

```bash
# Merge — creates a merge commit, preserves history
git checkout main
git merge feature/incremental-orders
git merge --no-ff feature/branch        # always create a merge commit
git merge --squash feature/branch       # squash all commits into one staged change

# Rebase — replays your commits on top of another branch (linear history)
git checkout feature/my-branch
git rebase main            # replay feature commits on top of latest main

# Interactive rebase — rewrite, squash, or reorder commits
git rebase -i HEAD~3       # rewrite last 3 commits
# Commands: pick, squash (s), reword (r), drop (d), fixup (f)

# Resolve merge conflicts
# Git marks conflicts in the file:
# <<<<<<< HEAD (your changes)
# your changes
# =======
# their changes
# >>>>>>> feature/branch (incoming)

# After resolving:
git add resolved_file.sql
git merge --continue       # or: git rebase --continue

# Abort if it gets messy
git merge --abort
git rebase --abort
```

### When to use which

| | Merge | Rebase |
|--|-------|--------|
| **History** | Non-linear (merge commits) | Linear |
| **Shared branches** | Yes | No — never rebase shared/public branches |
| **Feature branches** | Both work | Rebase on main before PR = clean history |
| **Hotfixes** | Merge | Not typical |

---

## Undoing Changes

```bash
# Discard unstaged changes in a file
git restore file.py                   # modern syntax
git checkout -- file.py               # old syntax

# Discard all unstaged changes
git restore .

# Unstage (remove from staging area, keep changes)
git restore --staged file.py
git reset HEAD file.py               # old syntax

# Undo last commit, keep changes staged
git reset --soft HEAD~1

# Undo last commit, keep changes unstaged
git reset HEAD~1

# Undo last commit, DISCARD changes (DESTRUCTIVE)
git reset --hard HEAD~1

# Revert a commit (safe — creates a new commit that undoes it)
git revert abc1234                   # use on shared/public branches

# Stash — save work temporarily without committing
git stash                            # stash current changes
git stash push -m "WIP: orders fix"  # stash with a name
git stash list                       # list stashes
git stash pop                        # apply latest stash and remove it
git stash apply stash@{1}            # apply specific stash, keep it
git stash drop stash@{1}             # delete a stash
git stash branch feature/recover     # create branch from stash
```

---

## .gitignore for DE Projects

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
venv/
.env
*.egg-info/
dist/
build/
.pytest_cache/
.mypy_cache/

# Jupyter
.ipynb_checkpoints/
*.ipynb_metadata

# dbt
target/               # compiled SQL and run artifacts
dbt_packages/         # installed packages (like node_modules)
logs/
.dbt/                 # local profiles (if inside project)

# Airflow
logs/
airflow.db
airflow.cfg           # may contain local config

# Data files — never commit large data
*.csv
*.parquet
*.json
*.avro
*.orc
data/
raw/
output/

# Secrets — NEVER commit these
.env
*.pem
*.key
secrets/
credentials.json
service_account.json
~/.aws/credentials    # (gitignore on system level)

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
*.swo

# Terraform
.terraform/
*.tfstate
*.tfstate.backup
terraform.tfvars      # often contains secrets
```

---

## Git Workflow for Data Teams

### Trunk-based development (recommended for data teams)

```
main (always deployable)
  ↑
  ├── feature/DE-123-add-orders-pipeline  (short-lived, < 1-2 days)
  ├── fix/DE-124-null-in-join             (short-lived)
  └── feature/DE-125-kafka-consumer       (short-lived)

PR → review → squash merge → delete branch
```

### Feature branch workflow

```bash
# 1. Start from latest main
git checkout main
git pull origin main

# 2. Create a feature branch
git checkout -b feature/DE-123-incremental-orders

# 3. Work, commit often (small, atomic commits)
git add models/marts/fct_orders.sql
git commit -m "feat: add incremental strategy to fct_orders"

git add tests/
git commit -m "test: add row count assertion for fct_orders"

# 4. Keep branch up to date with main
git fetch origin
git rebase origin/main   # or: git merge origin/main

# 5. Push and open a PR
git push -u origin feature/DE-123-incremental-orders
# Open PR on GitHub/GitLab

# 6. After PR approval — squash merge into main
# (done via GitHub UI or CLI)
gh pr merge 42 --squash --delete-branch

# 7. Sync local main
git checkout main && git pull
```

---

## Git for dbt Projects

### Repo structure

```
dbt-project/
  ├── models/
  │   ├── staging/
  │   ├── intermediate/
  │   └── marts/
  ├── tests/
  ├── macros/
  ├── seeds/
  ├── snapshots/
  ├── dbt_project.yml
  ├── packages.yml
  └── .gitignore           # include target/, dbt_packages/, logs/
```

### CI/CD for dbt

```yaml
# .github/workflows/dbt_ci.yml
name: dbt CI

on:
  pull_request:
    paths:
      - 'models/**'
      - 'tests/**'
      - 'macros/**'
      - 'dbt_project.yml'

jobs:
  dbt_test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dbt
        run: pip install dbt-snowflake==1.7.0

      - name: dbt debug
        run: dbt debug
        env:
          SNOWFLAKE_USER: ${{ secrets.SNOWFLAKE_USER }}
          SNOWFLAKE_PASSWORD: ${{ secrets.SNOWFLAKE_PASSWORD }}

      # Only run models changed in this PR
      - name: dbt build (slim CI)
        run: |
          dbt build \
            --select state:modified+ \
            --defer \
            --state ./prod_artifacts/
        env:
          SNOWFLAKE_USER: ${{ secrets.SNOWFLAKE_USER }}
          SNOWFLAKE_PASSWORD: ${{ secrets.SNOWFLAKE_PASSWORD }}
```

### Dev → prod promotion

```bash
# Dev workflow
dbt run --target dev --select my_new_model+
dbt test --target dev --select my_new_model+

# CI (on PR)
dbt build --target ci --select state:modified+ --defer --state ./prod_artifacts/

# Prod deploy (on merge to main)
dbt build --target prod --select state:modified+
```

---

## Git Hooks in Pipelines

Git hooks are scripts that run automatically at certain Git events.

```bash
# Pre-commit hook — run linting/tests before every commit
# File: .git/hooks/pre-commit (chmod +x)

#!/usr/bin/env bash
set -e

echo "Running pre-commit checks..."

# dbt compile check
if [ -d "models" ]; then
    dbt compile --quiet || { echo "dbt compile failed"; exit 1; }
fi

# Python linting
if command -v ruff &> /dev/null; then
    ruff check . || { echo "Ruff linting failed"; exit 1; }
fi

# Check for secrets
if git diff --cached | grep -E "(password|secret|api_key)\s*=\s*['\"]" ; then
    echo "Potential secret detected in diff. Aborting."
    exit 1
fi

echo "All checks passed."
```

```bash
# pre-commit framework — manage hooks as config
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-yaml
      - id: detect-private-key
      - id: check-added-large-files
        args: ['--maxkb=500']

# Install
pip install pre-commit
pre-commit install         # installs into .git/hooks/pre-commit
pre-commit run --all-files # run manually
```

---

## Useful Aliases & Tips

```bash
# Add to ~/.gitconfig or ~/.bashrc

# Git aliases
git config --global alias.st   "status"
git config --global alias.co   "checkout"
git config --global alias.br   "branch"
git config --global alias.lg   "log --oneline --graph --all --decorate"
git config --global alias.last "log -1 HEAD"
git config --global alias.undo "reset HEAD~1 --mixed"
git config --global alias.unstage "restore --staged"

# Bash aliases
alias gs="git status"
alias ga="git add"
alias gc="git commit -m"
alias gp="git push"
alias gl="git log --oneline --graph --all"
alias gco="git checkout"
alias gcb="git checkout -b"

# Find which branch introduced a bug
git bisect start
git bisect bad                   # current commit is broken
git bisect good abc1234          # this commit was good
# Git checks out midpoint — test and mark good/bad until bug commit found
git bisect reset                 # end bisect

# Search commit history for a string
git log -S "function_name" --oneline          # commits that added/removed string
git log --all --grep="fix orders"             # commits with message matching

# Show file history
git log --follow -p models/fct_orders.sql    # full diff history of a file
git log --follow --oneline models/fct_orders.sql

# Recover a deleted branch (if you know the commit hash)
git reflog                        # shows all recent HEAD movements
git checkout -b recovered abc1234 # create branch from that commit
```
