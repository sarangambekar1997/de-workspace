# Terraform for Data Engineers
> Provision and manage cloud data infrastructure as code — S3, IAM, Snowflake, Databricks, and more.

**Prerequisites:** [Cloud Storage](../01-storage/cloud-storage.md) · [Git for DE](../00-foundations/git-for-de.md)

**Related:** [Snowflake](../01-storage/snowflake-reference.md) · [Databricks](../02-processing/databricks-reference.md) · [Docker](docker-reference.md) · [Glossary](../99-reference/glossary.md)

---

## Table of Contents

**Basic**
- [Why Infrastructure as Code](#why-infrastructure-as-code)
- [Terraform Concepts](#terraform-concepts)
- [Setup & First Resource](#setup--first-resource)
- [Core CLI Commands](#core-cli-commands)

**Intermediate**
- [Variables & Outputs](#variables--outputs)
- [Modules](#modules)
- [Remote State](#remote-state)
- [AWS Resources for DE](#aws-resources-for-de)

**Advanced**
- [Snowflake with Terraform](#snowflake-with-terraform)
- [Databricks with Terraform](#databricks-with-terraform)
- [Airflow Infra on AWS](#airflow-infra-on-aws)
- [Common Mistakes](#common-mistakes)

---

## Why Infrastructure as Code

```
Without IaC:
  Engineer A creates an S3 bucket manually via the AWS console
  Engineer B creates a similar bucket differently — different naming, no encryption
  3 months later: nobody knows what exists, what settings were used, or who owns what
  Deleting the wrong bucket means data loss

With IaC (Terraform):
  All infrastructure is defined in .tf files in the repo
  Changes go through PR review (same as code)
  `terraform apply` brings any environment to the defined state
  Destroyed and recreated resources are identical every time
  State file tracks what exists — safe to destroy, safe to recreate
```

**Benefits for data teams specifically:**
- Reproduce dev/staging/prod environments from the same code
- Manage Snowflake roles, databases, warehouses without clicking around the UI
- Provision Databricks workspaces, clusters, and secrets programmatically
- IAM policies as code — auditable, reviewable, version-controlled

---

## Terraform Concepts

| Concept | Description |
|---------|-------------|
| **Provider** | Plugin that talks to a cloud API (AWS, Snowflake, Databricks) |
| **Resource** | An infrastructure object to create (S3 bucket, IAM role, Snowflake database) |
| **Data source** | Read existing infrastructure without managing it |
| **Variable** | Input parameter (like a function argument) |
| **Output** | Exported value (like a return value) |
| **Module** | Reusable group of resources (like a function) |
| **State** | File tracking what Terraform has created — never edit manually |
| **Plan** | Preview of what `terraform apply` will create/update/destroy |
| **Backend** | Where the state file lives (S3, Terraform Cloud, local) |

```
Workflow:
  Write .tf files → terraform init → terraform plan → terraform apply
                                         ↑ review diff ↑        ↑ confirm
```

---

## Setup & First Resource

```bash
# Install Terraform (macOS)
brew install terraform

# Install Terraform (Linux)
wget https://releases.hashicorp.com/terraform/1.7.0/terraform_1.7.0_linux_amd64.zip
unzip terraform_1.7.0_linux_amd64.zip
mv terraform /usr/local/bin/

# Verify
terraform version
```

### Project structure

```
infra/
  ├── main.tf          # core resources
  ├── variables.tf     # input variables
  ├── outputs.tf       # output values
  ├── providers.tf     # provider configuration
  ├── terraform.tfvars # variable values (DO NOT COMMIT secrets)
  └── modules/
      ├── s3-data-lake/
      └── snowflake-env/
```

### First resource — S3 bucket

```hcl
# providers.tf
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.5.0"
}

provider "aws" {
  region = "us-east-1"
}

# main.tf
resource "aws_s3_bucket" "data_lake" {
  bucket = "mycompany-data-lake-prod"

  tags = {
    Environment = "prod"
    Team        = "data-engineering"
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket                  = aws_s3_bucket.data_lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

---

## Core CLI Commands

```bash
# Initialize — download providers, set up backend
terraform init

# Preview changes — never skips this step
terraform plan

# Apply changes (prompts for confirmation)
terraform apply

# Apply without prompt (use in CI only)
terraform apply -auto-approve

# Destroy all resources managed by this config (DANGEROUS)
terraform destroy

# Format all .tf files
terraform fmt

# Validate syntax and configuration
terraform validate

# Show current state
terraform show

# List all resources in state
terraform state list

# Import an existing resource into state
terraform import aws_s3_bucket.data_lake mycompany-data-lake-prod

# Target a specific resource (useful for debugging)
terraform apply -target=aws_s3_bucket.data_lake

# View outputs
terraform output
terraform output bucket_arn   # specific output
```

---

## Variables & Outputs

```hcl
# variables.tf
variable "environment" {
  description = "Deployment environment"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod"
  }
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "bucket_name" {
  description = "S3 bucket name"
  type        = string
}

variable "tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default     = {}
}

variable "snowflake_account" {
  description = "Snowflake account identifier"
  type        = string
  sensitive   = true   # redacted in logs and state display
}
```

```hcl
# terraform.tfvars (DO NOT commit to git — add to .gitignore)
environment       = "prod"
bucket_name       = "mycompany-data-lake-prod"
snowflake_account = "myaccount.us-east-1"
```

```hcl
# Reference variables in resources
resource "aws_s3_bucket" "data_lake" {
  bucket = var.bucket_name
  tags   = merge(var.tags, { Environment = var.environment })
}

# outputs.tf
output "bucket_arn" {
  description = "ARN of the data lake S3 bucket"
  value       = aws_s3_bucket.data_lake.arn
}

output "bucket_name" {
  value = aws_s3_bucket.data_lake.bucket
}
```

---

## Modules

Reusable groups of resources — like functions for infrastructure.

```hcl
# modules/s3-data-lake/main.tf
variable "bucket_name"  { type = string }
variable "environment"  { type = string }
variable "layers"       { type = list(string); default = ["bronze", "silver", "gold"] }

resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name
  tags   = { Environment = var.environment, ManagedBy = "terraform" }
}

# Create folder structure via lifecycle marker objects
resource "aws_s3_object" "layer_folders" {
  for_each = toset(var.layers)
  bucket   = aws_s3_bucket.this.id
  key      = "${each.value}/"
  content  = ""
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

output "bucket_arn"  { value = aws_s3_bucket.this.arn }
output "bucket_name" { value = aws_s3_bucket.this.bucket }
```

```hcl
# main.tf — using the module
module "data_lake_prod" {
  source      = "./modules/s3-data-lake"
  bucket_name = "mycompany-data-lake-prod"
  environment = "prod"
  layers      = ["bronze", "silver", "gold", "archive"]
}

module "data_lake_dev" {
  source      = "./modules/s3-data-lake"
  bucket_name = "mycompany-data-lake-dev"
  environment = "dev"
}

# Reference module outputs
output "prod_bucket_arn" {
  value = module.data_lake_prod.bucket_arn
}
```

---

## Remote State

State must live somewhere shared — not on a local laptop.

```hcl
# backend.tf — store state in S3 with DynamoDB locking
terraform {
  backend "s3" {
    bucket         = "mycompany-terraform-state"
    key            = "data-platform/prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"   # prevents concurrent applies
  }
}
```

```bash
# Create the state bucket and lock table BEFORE init (do this once manually or with a bootstrap script)
aws s3api create-bucket --bucket mycompany-terraform-state --region us-east-1
aws s3api put-bucket-versioning --bucket mycompany-terraform-state --versioning-configuration Status=Enabled
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

---

## AWS Resources for DE

### S3 data lake with IAM

```hcl
# Full data lake setup: bucket + IAM role for pipeline access

resource "aws_s3_bucket" "data_lake" {
  bucket = "mycompany-data-lake-${var.environment}"
}

# Lifecycle policy: move old data to cheaper storage
resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    id     = "bronze-lifecycle"
    status = "Enabled"
    filter { prefix = "bronze/" }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
    expiration { days = 365 }
  }
}

# IAM role for the data pipeline (Airflow, Glue, etc.)
resource "aws_iam_role" "data_pipeline" {
  name = "data-pipeline-role-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_policy" "data_lake_access" {
  name = "data-lake-access-${var.environment}"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.data_lake.arn,
          "${aws_s3_bucket.data_lake.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "data_pipeline" {
  role       = aws_iam_role.data_pipeline.name
  policy_arn = aws_iam_policy.data_lake_access.arn
}
```

### Secrets Manager

```hcl
# Store pipeline credentials in AWS Secrets Manager
resource "aws_secretsmanager_secret" "snowflake_creds" {
  name        = "/data-platform/${var.environment}/snowflake"
  description = "Snowflake credentials for data pipeline"
}

resource "aws_secretsmanager_secret_version" "snowflake_creds" {
  secret_id = aws_secretsmanager_secret.snowflake_creds.id
  secret_string = jsonencode({
    account  = var.snowflake_account
    username = var.snowflake_username
    [REDACTED_SQL_PASSWORD_1]word = var.snowflake_[REDACTED_SQL_PASSWORD_1]word    # pass via env var, never hardcode
  })
}

output "snowflake_secret_arn" {
  value = aws_secretsmanager_secret.snowflake_creds.arn
}
```

---

## Snowflake with Terraform

```hcl
# providers.tf — add Snowflake provider
terraform {
  required_providers {
    snowflake = {
      source  = "Snowflake-Labs/snowflake"
      version = "~> 0.89"
    }
  }
}

provider "snowflake" {
  account  = var.snowflake_account
  username = var.snowflake_username
  [REDACTED_SQL_PASSWORD_1]word = var.snowflake_[REDACTED_SQL_PASSWORD_1]word      # use env: SNOWFLAKE_PASSWORD
  role     = "SYSADMIN"
}

# Databases
resource "snowflake_database" "raw" {
  name    = "RAW_${upper(var.environment)}"
  comment = "Raw ingested data — bronze layer"
}

resource "snowflake_database" "analytics" {
  name    = "ANALYTICS_${upper(var.environment)}"
  comment = "Transformed data — silver and gold layers"
}

# Schemas
resource "snowflake_schema" "raw_orders" {
  database = snowflake_database.raw.name
  name     = "ORDERS"
}

resource "snowflake_schema" "marts" {
  database = snowflake_database.analytics.name
  name     = "MARTS"
}

# Virtual warehouses
resource "snowflake_warehouse" "transform" {
  name           = "TRANSFORM_WH_${upper(var.environment)}"
  warehouse_size = var.environment == "prod" ? "MEDIUM" : "X-SMALL"
  auto_suspend   = 60
  auto_resume    = true
  comment        = "Used by dbt transformations"
}

resource "snowflake_warehouse" "reporting" {
  name           = "REPORTING_WH_${upper(var.environment)}"
  warehouse_size = "SMALL"
  auto_suspend   = 300
  auto_resume    = true
}

# Roles
resource "snowflake_role" "analyst" {
  name    = "ANALYST_${upper(var.environment)}"
  comment = "Read access to gold layer tables"
}

resource "snowflake_role" "transformer" {
  name    = "TRANSFORMER_${upper(var.environment)}"
  comment = "Used by dbt to run transformations"
}

# Grants
resource "snowflake_grant_privileges_to_role" "analyst_select" {
  role_name  = snowflake_role.analyst.name
  privileges = ["SELECT"]
  on_schema_object {
    future_objects_in_schema {
      object_type_plural = "TABLES"
      database           = snowflake_database.analytics.name
      schema             = snowflake_schema.marts.name
    }
  }
}

resource "snowflake_grant_privileges_to_role" "transformer_all" {
  role_name  = snowflake_role.transformer.name
  privileges = ["ALL PRIVILEGES"]
  on_schema {
    database  = snowflake_database.analytics.name
    schema_name = snowflake_schema.marts.name
  }
}

# Service account user for dbt
resource "snowflake_user" "dbt_service_account" {
  name         = "DBT_SA_${upper(var.environment)}"
  login_name   = "dbt_sa_${var.environment}"
  default_role = snowflake_role.transformer.name
  default_warehouse = snowflake_warehouse.transform.name
  must_change_[REDACTED_SQL_PASSWORD_1]word = false
}

resource "snowflake_grant_account_role" "dbt_sa_role" {
  role_name = snowflake_role.transformer.name
  user_name = snowflake_user.dbt_service_account.name
}
```

---

## Databricks with Terraform

```hcl
# providers.tf
terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.40"
    }
  }
}

provider "databricks" {
  host  = var.databricks_host    # e.g. https://adb-xxx.azuredatabricks.net
  token = var.databricks_token   # use env: DATABRICKS_TOKEN
}

# Cluster
resource "databricks_cluster" "etl" {
  cluster_name            = "etl-cluster-${var.environment}"
  spark_version           = "14.3.x-scala2.12"
  node_type_id            = var.environment == "prod" ? "Standard_DS3_v2" : "Standard_DS3_v2"
  autotermination_minutes = 30

  autoscale {
    min_workers = 2
    max_workers = 8
  }

  spark_conf = {
    "spark.databricks.delta.preview.enabled" = "true"
  }

  library {
    pypi { package = "dbt-databricks==1.7.0" }
  }
}

# Secrets scope (backed by Azure Key Vault or Databricks-managed)
resource "databricks_secret_scope" "pipeline_secrets" {
  name = "pipeline-secrets-${var.environment}"
}

resource "databricks_secret" "snowflake_[REDACTED_SQL_PASSWORD_1]word" {
  key          = "snowflake-[REDACTED_SQL_PASSWORD_1]word"
  string_value = var.snowflake_[REDACTED_SQL_PASSWORD_1]word
  scope        = databricks_secret_scope.pipeline_secrets.name
}

# Job
resource "databricks_job" "daily_pipeline" {
  name = "daily-orders-pipeline-${var.environment}"

  task {
    task_key = "load_bronze"
    existing_cluster_id = databricks_cluster.etl.id
    notebook_task {
      notebook_path = "/Repos/data-team/pipelines/bronze/load_orders"
    }
  }

  task {
    task_key = "transform_silver"
    depends_on { task_key = "load_bronze" }
    existing_cluster_id = databricks_cluster.etl.id
    notebook_task {
      notebook_path = "/Repos/data-team/pipelines/silver/transform_orders"
    }
  }

  schedule {
    quartz_cron_expression = "0 0 2 * * ?"   # 2am daily
    timezone_id            = "UTC"
    pause_status           = var.environment == "prod" ? "UNPAUSED" : "PAUSED"
  }
}

# Unity Catalog
resource "databricks_catalog" "main" {
  name    = "main"
  comment = "Main data catalog"
}

resource "databricks_schema" "bronze" {
  catalog_name = databricks_catalog.main.name
  name         = "bronze"
  comment      = "Raw ingested data"
}

resource "databricks_grants" "bronze_schema" {
  schema = "${databricks_catalog.main.name}.${databricks_schema.bronze.name}"
  grant {
    principal  = "data-engineers@mycompany.com"
    privileges = ["USE_SCHEMA", "CREATE_TABLE", "SELECT"]
  }
}
```

---

## Airflow Infra on AWS

```hcl
# MWAA (Managed Workflows for Apache Airflow) on AWS

resource "aws_s3_bucket" "airflow" {
  bucket = "mycompany-airflow-${var.environment}"
}

resource "aws_s3_object" "dags_folder" {
  bucket  = aws_s3_bucket.airflow.id
  key     = "dags/"
  content = ""
}

resource "aws_s3_object" "requirements" {
  bucket = aws_s3_bucket.airflow.id
  key    = "requirements.txt"
  source = "${path.module}/requirements.txt"
  etag   = filemd5("${path.module}/requirements.txt")
}

resource "aws_mwaa_environment" "airflow" {
  name               = "mycompany-airflow-${var.environment}"
  airflow_version    = "2.8.1"
  environment_class  = var.environment == "prod" ? "mw1.medium" : "mw1.small"
  execution_role_arn = aws_iam_role.mwaa.arn

  source_bucket_arn     = aws_s3_bucket.airflow.arn
  dag_s3_path           = "dags/"
  requirements_s3_path  = "requirements.txt"

  airflow_configuration_options = {
    "core.default_timezone"      = "UTC"
    "scheduler.dag_dir_list_interval" = "30"
    "webserver.dag_default_view" = "graph"
  }

  network_configuration {
    security_group_ids = [aws_security_group.mwaa.id]
    subnet_ids         = var.private_subnet_ids
  }

  logging_configuration {
    dag_processing_logs  { enabled = true; log_level = "WARNING" }
    scheduler_logs       { enabled = true; log_level = "WARNING" }
    task_logs            { enabled = true; log_level = "INFO" }
    webserver_logs       { enabled = true; log_level = "WARNING" }
    worker_logs          { enabled = true; log_level = "WARNING" }
  }
}
```

---

## Common Mistakes

```
1. Committing terraform.tfvars or .tfstate to git
   Problem: exposes credentials and infrastructure details
   Fix:     Add to .gitignore; use remote backend for state;
            use env vars or Secrets Manager for sensitive values

2. No remote state backend
   Problem: two engineers applying at the same time = corrupted state
   Fix:     Always configure S3 + DynamoDB locking from day one

3. Using terraform destroy in production
   Problem: destroys everything, including live data
   Fix:     Use targeted destroy (-target), or set prevent_destroy = true
            on critical resources

4. Not running terraform plan before apply
   Problem: surprises — resources you didn't expect to be destroyed
   Fix:     Always review plan output; in CI, require plan before merge

5. Hardcoding account IDs and region strings
   Problem: not reusable across environments
   Fix:     Use data sources and variables

6. Single monolithic main.tf with 1000 lines
   Problem: hard to navigate, long plans, blast radius too large
   Fix:     Split by service (s3.tf, iam.tf, snowflake.tf, databricks.tf)
            or by lifecycle (long-lived vs frequently-changed resources)

7. Not using lifecycle { prevent_destroy = true } on data resources
   Problem: a typo in bucket_name causes Terraform to destroy and recreate
   Fix:
   resource "aws_s3_bucket" "data_lake" {
     bucket = "mycompany-data-lake-prod"
     lifecycle { prevent_destroy = true }
   }

8. Importing existing resources manually instead of into state
   Problem: Terraform thinks the resource doesn't exist → tries to create → conflict
   Fix:     terraform import aws_s3_bucket.data_lake mycompany-data-lake-prod
```

### .gitignore for Terraform

```gitignore
# Terraform state — never commit
*.tfstate
*.tfstate.*
.terraform/
.terraform.lock.hcl   # OK to commit this one if you want pinned versions
terraform.tfvars      # contains secrets — use .tfvars.example instead
*.tfvars.backup
crash.log
override.tf
override.tf.json
```

---

**Previous:** [Docker](docker-reference.md) · **Next:** [Snowflake](../01-storage/snowflake-reference.md) · **Back to:** [Index](../README.md)
