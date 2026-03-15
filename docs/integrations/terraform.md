# Terraform Integration

FaultZero can import infrastructure models directly from Terraform configuration files and state, enabling resilience evaluation before deployment.

## Setup

No additional dependencies are required. Terraform integration is included in the base FaultZero installation.

## Import from Terraform files

### HCL configuration files

```bash
faultzero tf-import --dir ./terraform --output tf-model.json
```

### Terraform state

```bash
faultzero tf-import --state terraform.tfstate --output tf-model.json
```

### Remote state (S3)

```bash
faultzero tf-import --state s3://my-bucket/terraform.tfstate --output tf-model.json
```

## Supported Resources

FaultZero parses the following Terraform resource types:

| Provider | Resources |
|----------|-----------|
| AWS | `aws_instance`, `aws_db_instance`, `aws_lb`, `aws_elasticache_cluster`, `aws_s3_bucket`, `aws_cloudfront_distribution`, `aws_ecs_service`, `aws_lambda_function` |
| GCP | `google_compute_instance`, `google_sql_database_instance`, `google_compute_forwarding_rule`, `google_redis_instance` |
| Azure | `azurerm_virtual_machine`, `azurerm_sql_server`, `azurerm_lb`, `azurerm_redis_cache` |
| Kubernetes | `kubernetes_deployment`, `kubernetes_service`, `kubernetes_ingress` |

## CI/CD Usage

Gate Terraform applies on resilience score:

```hcl
# In your CI pipeline
resource "null_resource" "resilience_check" {
  provisioner "local-exec" {
    command = "faultzero tf-import --dir . --output /tmp/model.json && faultzero evaluate -m /tmp/model.json --threshold 70"
  }
}
```

## Example: Pre-apply validation

```bash
# Plan changes
terraform plan -out=tfplan

# Import current + planned state
faultzero tf-import --dir . --output current.json
faultzero tf-import --plan tfplan --output planned.json

# Compare resilience impact
faultzero diff current.json planned.json --only-regressions
```

If regressions are detected, the diff command exits with code 2, allowing CI/CD pipelines to block the apply.
