# Docker Reference
> From first container to production-ready data pipeline environments.

---

## Table of Contents

**Basics**
- [What is Docker?](#what-is-docker)
- [Core Concepts](#core-concepts)
- [Essential CLI Commands](#essential-cli-commands)
- [Dockerfile](#dockerfile)
- [Images & Layers](#images--layers)

**Intermediate**
- [Volumes & Bind Mounts](#volumes--bind-mounts)
- [Networking](#networking)
- [Environment Variables & Secrets](#environment-variables--secrets)
- [Docker Compose](#docker-compose)

**Advanced**
- [Multi-Stage Builds](#multi-stage-builds)
- [Docker for DE Pipelines](#docker-for-de-pipelines)
- [Running Airflow in Docker](#running-airflow-in-docker)
- [Best Practices](#best-practices)

---

## What is Docker?

Docker packages an application and all its dependencies (libraries, configs, runtime) into a **container** — an isolated, reproducible environment that runs the same on any machine.

```
Without Docker:               With Docker:
"Works on my machine"  →      Runs identically everywhere
Manual dependency install →   One command: docker run
"Python 3.8 or 3.11?" →       Pinned inside the container
Dev ≠ Prod environment →      Same image everywhere
```

### VM vs Container

```
Virtual Machine:              Container:
┌─────────────────┐           ┌─────────────────┐
│   App           │           │   App           │
│   Libraries     │           │   Libraries     │
│   Guest OS      │  heavy    │   ─────────     │  lightweight
│   Hypervisor    │  slow     │   Docker Engine │  fast
│   Host OS       │           │   Host OS       │
└─────────────────┘           └─────────────────┘
   ~GB, minutes to start         ~MB, seconds to start
```

---

## Core Concepts

| Concept | Definition |
|---------|-----------|
| **Image** | A read-only template — the blueprint for a container. Built from a Dockerfile |
| **Container** | A running instance of an image — isolated process with its own filesystem |
| **Dockerfile** | A text file with instructions to build an image |
| **Registry** | A repository for images (Docker Hub, ECR, GCR, GHCR) |
| **Layer** | Each Dockerfile instruction creates a cached layer; layers are shared across images |
| **Volume** | Persistent storage that outlives the container |
| **Bind mount** | Mount a host directory into a container |
| **Network** | Virtual network connecting containers |
| **docker-compose** | Tool to define and run multi-container applications via YAML |

---

## Essential CLI Commands

```bash
# ── Images ────────────────────────────────────────
docker pull python:3.11-slim          # download image from registry
docker images                          # list local images
docker rmi python:3.11-slim           # delete image
docker image prune                     # delete dangling images

# ── Containers ────────────────────────────────────
docker run python:3.11-slim            # create + start container (foreground)
docker run -d python:3.11-slim sleep infinity   # -d = detached (background)
docker run -it python:3.11-slim bash   # -it = interactive terminal
docker run --rm python:3.11-slim python -c "print('hello')"  # --rm = auto-delete on exit

docker ps                    # list running containers
docker ps -a                 # list all containers (including stopped)
docker stop <id or name>     # graceful stop (SIGTERM → SIGKILL after timeout)
docker kill <id or name>     # immediate stop (SIGKILL)
docker rm <id or name>       # delete container
docker rm $(docker ps -aq)   # delete all stopped containers

# ── Exec into a running container ─────────────────
docker exec -it <container_id> bash    # open bash shell
docker exec <container_id> python manage.py migrate

# ── Logs ──────────────────────────────────────────
docker logs <container_id>
docker logs -f <container_id>          # follow (tail -f)
docker logs --tail 100 <container_id>

# ── Build ─────────────────────────────────────────
docker build -t myapp:1.0 .            # build from ./Dockerfile, tag as myapp:1.0
docker build -t myapp:1.0 -f docker/Dockerfile .   # custom Dockerfile path
docker build --no-cache -t myapp:1.0 . # rebuild without layer cache

# ── Push to registry ──────────────────────────────
docker tag myapp:1.0 myrepo/myapp:1.0
docker push myrepo/myapp:1.0

# ── System cleanup ────────────────────────────────
docker system prune           # remove unused images, containers, networks
docker system prune -a        # also remove unused images (not just dangling)
docker system df              # show disk usage
```

---

## Dockerfile

```dockerfile
# Base image — always pin a specific version tag, never use :latest
FROM python:3.11-slim

# Metadata
LABEL maintainer="data-engineering@mycompany.com"
LABEL version="1.0"

# Set working directory inside the container
WORKDIR /app

# Copy dependency files first (leverages layer caching)
# If requirements.txt doesn't change, this layer is cached
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Environment variables with defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO

# Expose a port (documentation only — doesn't actually publish)
EXPOSE 8080

# Create a non-root user (security best practice)
RUN useradd -m -u 1000 appuser
USER appuser

# Default command when container starts
CMD ["python", "src/main.py"]

# Or use ENTRYPOINT for fixed command + CMD for default args
ENTRYPOINT ["python", "src/pipeline.py"]
CMD ["--mode", "daily"]     # can be overridden at runtime
```

### RUN vs CMD vs ENTRYPOINT

| Instruction | When it runs | Can be overridden? |
|-------------|-------------|-------------------|
| `RUN` | At build time — creates a layer | No |
| `CMD` | Container start — default command | Yes (`docker run myapp custom_command`) |
| `ENTRYPOINT` | Container start — fixed executable | Hard to override (use `--entrypoint`) |

---

## Images & Layers

```dockerfile
# Each instruction = a new layer
FROM python:3.11-slim         # Layer 1 (base)
WORKDIR /app                   # Layer 2
COPY requirements.txt .        # Layer 3
RUN pip install -r requirements.txt  # Layer 4  ← expensive, cache this
COPY src/ .                    # Layer 5  ← code changes often; goes last
```

**Layer caching rule:** Docker reuses a cached layer if the instruction AND all previous layers are unchanged. Put frequently-changing steps (COPY source code) AFTER rarely-changing steps (pip install).

```dockerfile
# Bad order — any code change busts the pip install cache
COPY . .
RUN pip install -r requirements.txt

# Good order — code changes don't invalidate pip cache
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
```

---

## Volumes & Bind Mounts

```bash
# Named volume — managed by Docker, persists across container restarts
docker run -v mydata:/app/data myapp

# Bind mount — mount a host directory
docker run -v /host/path:/container/path myapp
docker run -v $(pwd)/data:/app/data myapp   # current directory

# Read-only bind mount
docker run -v $(pwd)/config:/app/config:ro myapp

# List volumes
docker volume ls
docker volume inspect mydata
docker volume rm mydata
```

### When to use each

| | Named Volume | Bind Mount |
|--|-------------|-----------|
| Data managed by Docker? | Yes | No — you control the host path |
| Dev: hot reload code changes? | No | Yes — edit on host, reflects in container |
| Production data persistence? | Yes | Depends on host path |
| Works on all OS? | Yes | Path differences on Windows |

---

## Networking

```bash
# Create a network
docker network create my-network

# Connect containers to a network
docker run -d --name postgres --network my-network postgres:15
docker run -d --name airflow  --network my-network apache/airflow:2.9.0

# Containers on the same network can reach each other by name
# Inside the airflow container: connect to "postgres:5432"

# Publish a port — map host port to container port
docker run -p 8080:8080 myapp     # host:container
docker run -p 5432:5432 postgres

# List networks
docker network ls
docker network inspect my-network
```

---

## Environment Variables & Secrets

```bash
# Pass env vars at runtime
docker run -e DB_HOST=localhost -e DB_PORT=5432 myapp

# Load from a .env file
docker run --env-file .env myapp

# .env file format
DB_HOST=localhost
DB_PORT=5432
DB_PASSWORD=secret
```

```dockerfile
# In Dockerfile — build-time defaults (don't put secrets here)
ENV DB_PORT=5432
ENV LOG_LEVEL=INFO

# Never hardcode secrets in a Dockerfile or commit .env files
# Use Docker secrets (Swarm) or mount secrets at runtime
```

---

## Docker Compose

Docker Compose defines multi-container applications in a single YAML file.

```yaml
# docker-compose.yml
version: "3.9"

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "airflow"]
      interval: 10s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  myapp:
    build:
      context: .
      dockerfile: Dockerfile
    image: myapp:latest
    depends_on:
      postgres:
        condition: service_healthy    # wait for healthcheck to pass
    environment:
      - DB_HOST=postgres             # use service name as hostname
      - DB_PORT=5432
    env_file:
      - .env                         # load additional vars from .env
    volumes:
      - ./src:/app/src                # bind mount for development
      - ./logs:/app/logs
    ports:
      - "8080:8080"
    restart: unless-stopped          # auto-restart on failure

volumes:
  postgres_data:                     # named volume declaration
```

```bash
# Docker Compose commands
docker compose up                    # start all services (foreground)
docker compose up -d                 # start in background
docker compose up --build            # rebuild images before starting
docker compose down                  # stop and remove containers
docker compose down -v               # also remove volumes
docker compose logs -f myapp         # follow logs for one service
docker compose exec myapp bash       # open shell in running service
docker compose ps                    # list service status
docker compose restart myapp         # restart one service
docker compose pull                  # pull latest images
```

---

## Multi-Stage Builds

Reduce final image size by building in one stage and copying only the output to a lean final image.

```dockerfile
# Stage 1: build
FROM python:3.11 AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# Stage 2: runtime — lean final image
FROM python:3.11-slim AS runtime
WORKDIR /app

# Copy only installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY src/ ./src/

RUN useradd -m appuser
USER appuser

CMD ["python", "src/main.py"]

# Result: final image doesn't include build tools, pip cache, or intermediate files
# Typical reduction: 800 MB → 150 MB
```

---

## Docker for DE Pipelines

### Packaging a PySpark job

```dockerfile
FROM bitnami/spark:3.5

USER root
WORKDIR /opt/spark/jobs

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy job files
COPY jobs/ .

USER 1001

ENTRYPOINT ["spark-submit"]
CMD ["--master", "local[*]", "main.py"]
```

```bash
# Run the job
docker run --rm \
    -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
    -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
    -v $(pwd)/output:/output \
    spark-job:1.0 \
    --master local[*] \
    jobs/orders_etl.py \
    --date 2024-03-15
```

### Packaging a dbt project

```dockerfile
FROM ghcr.io/dbt-labs/dbt-snowflake:1.7.0

WORKDIR /usr/app/dbt
COPY . .

# profiles.yml will be mounted or env vars used at runtime
ENTRYPOINT ["dbt"]
CMD ["run"]
```

```bash
docker run --rm \
    -e SNOWFLAKE_USER=$SNOWFLAKE_USER \
    -e SNOWFLAKE_PASSWORD=$SNOWFLAKE_PASSWORD \
    -v ~/.dbt:/root/.dbt \
    my-dbt-project:latest \
    run --target prod --select marts.*
```

---

## Running Airflow in Docker

```yaml
# docker-compose.airflow.yml — simplified Airflow stack
version: "3.9"

x-airflow-common: &airflow-common
  image: apache/airflow:2.9.0
  environment:
    AIRFLOW__CORE__EXECUTOR: LocalExecutor
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
    AIRFLOW__CORE__FERNET_KEY: ""
    AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION: "true"
    AIRFLOW__CORE__LOAD_EXAMPLES: "false"
    _PIP_ADDITIONAL_REQUIREMENTS: "apache-airflow-providers-snowflake apache-airflow-providers-amazon"
  volumes:
    - ./dags:/opt/airflow/dags
    - ./logs:/opt/airflow/logs
    - ./plugins:/opt/airflow/plugins
  depends_on:
    postgres:
      condition: service_healthy

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "airflow"]
      interval: 5s
      retries: 5

  airflow-webserver:
    <<: *airflow-common
    command: webserver
    ports:
      - "8080:8080"

  airflow-scheduler:
    <<: *airflow-common
    command: scheduler

  airflow-init:
    <<: *airflow-common
    command: >
      bash -c "airflow db init &&
               airflow users create --username admin --password admin
               --firstname Admin --lastname User --role Admin
               --email admin@example.com"

volumes:
  postgres_data:
```

```bash
docker compose -f docker-compose.airflow.yml up -d
# Airflow UI: http://localhost:8080 (admin/admin)
```

---

## Best Practices

```dockerfile
# ✅ Pin base image versions
FROM python:3.11.7-slim-bookworm   # good
FROM python:latest                  # bad

# ✅ Use slim or alpine variants
FROM python:3.11-slim   # ~50 MB
FROM python:3.11        # ~350 MB
FROM python:3.11-alpine # ~20 MB (but may have glibc compatibility issues)

# ✅ One process per container
# Don't run both a web server and a background worker in one container
# Use separate services in docker-compose instead

# ✅ Non-root user
RUN useradd -m -u 1000 appuser
USER appuser

# ✅ .dockerignore — exclude files from build context
```

```text
# .dockerignore
.git
.env
__pycache__
*.pyc
*.pyo
.pytest_cache
.venv
venv
*.egg-info
dist
build
docs
tests
*.log
```

```dockerfile
# ✅ Minimize layers — combine related RUN commands
# Bad
RUN apt-get update
RUN apt-get install -y curl wget
RUN apt-get clean

# Good
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ✅ COPY only what's needed — not COPY . . blindly
COPY requirements.txt .
COPY src/ ./src/
COPY config/ ./config/

# ✅ Use healthchecks
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1
```
