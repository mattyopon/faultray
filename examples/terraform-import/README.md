# Terraform → topology import

`faultray import terraform` converts Terraform JSON into an editable
FaultRay topology YAML that plugs straight into the simulation pipeline.

## Usage

```bash
# From the current state
terraform show -json > state.json
faultray import terraform state.json

# From a plan (includes resources that are not applied yet)
terraform plan -out=plan.tfplan
terraform show -json plan.tfplan > plan.json
faultray import terraform plan.json -o topology.yaml

# A raw terraform.tfstate (version 4) also works
faultray import terraform terraform.tfstate

# Then review the YAML and simulate
faultray simulate -m terraform-topology.yaml
faultray evaluate -m terraform-topology.yaml
```

Try it on the sample in this directory:

```bash
faultray import terraform examples/terraform-import/sample-state.json \
    -o /tmp/topology.yaml
```

`sample-topology.yaml` is the committed output of exactly that command.

## What gets imported

| Terraform resource | Component type |
|---|---|
| `aws_lb` / `aws_alb` / `aws_elb` / CloudFront / API Gateway | `load_balancer` |
| `aws_instance`, `aws_autoscaling_group`, `aws_ecs_service`, `aws_eks_cluster` | `app_server` |
| `aws_lambda_function` | `serverless` |
| `aws_db_instance`, `aws_rds_cluster`, `aws_dynamodb_table` | `database` |
| `aws_elasticache_cluster` / `aws_elasticache_replication_group` | `cache` |
| `aws_sqs_queue`, `aws_sns_topic`, `aws_mq_broker` | `queue` |
| `aws_s3_bucket`, `aws_efs_file_system` | `storage` |
| `aws_route53_record` | `dns` |
| HTTPS URLs in Lambda / ECS task env vars (non-AWS hosts) | `external_api` |

Listeners, target groups, attachments, ECS task definitions, event source
mappings and `aws_rds_cluster_instance` are **not** emitted as components —
they are consumed as wiring evidence (and RDS cluster instances fold into
the cluster's replica count).

Fully managed services (S3, SQS, SNS, Route53, DynamoDB, CloudFront,
Lambda, API Gateway, EFS) carry their published AWS SLA as
`external_sla.provider_sla`, so the availability model's external-SLA layer
uses contractual floors — consistent with FaultRay's conservative
(floor-first) reporting policy.

## How dependencies are inferred (and why you should still review them)

Edges are emitted **only when the input contains evidence**:

1. explicit `configuration` references (plan JSON),
2. `depends_on` / tfstate instance dependencies,
3. attribute cross-references (ARN / endpoint / id substrings),
4. well-known wiring patterns — ALB listener → target group → target
   (direction fixed as *LB requires backend*), Lambda event source mappings
   (*consumer requires source*), API Gateway integrations.

There are no type-based guesses: two unrelated resources never get an
edge. Unknown dependency semantics default to `requires` — the
conservative choice for floor availability. Relax individual edges to
`optional` / `async` in the YAML where you know better (e.g. cache
fallbacks, fire-and-forget queues).

Known limits of the MVP:

- references that cross module boundaries through variables are not
  resolved;
- EC2 `user_data` is not scanned (base64);
- components with no evidence stay isolated and are listed for manual
  wiring — an isolated component still participates in single-failure
  scenarios but not in cascades.
