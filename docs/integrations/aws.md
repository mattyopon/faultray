# AWS Integration

FaultZero can automatically scan your AWS infrastructure and build a resilience model from live resources.

## Setup

Install the AWS extras:

```bash
pip install "faultzero[aws]"
```

Ensure AWS credentials are configured:

```bash
aws configure
# or
export AWS_PROFILE=my-profile
```

## Scanning

### Full account scan

```bash
faultzero scan --provider aws --output aws-infra.json
```

### Region-specific scan

```bash
faultzero scan --provider aws --region us-east-1 --output us-east.json
```

### Using a named profile

```bash
faultzero scan --provider aws --profile production --output prod.json
```

## Supported Services

FaultZero scans the following AWS services:

| Service | Component Type | Details |
|---------|---------------|---------|
| EC2 | Compute | Instances, ASGs, placement groups |
| RDS | Database | Instances, clusters, Multi-AZ, read replicas |
| ElastiCache | Cache | Redis/Memcached clusters, replication groups |
| ELB/ALB/NLB | Load Balancer | Target groups, health checks |
| S3 | Storage | Buckets, cross-region replication |
| Route 53 | DNS | Hosted zones, health checks, failover policies |
| CloudFront | CDN | Distributions, origins, failover |
| ECS/EKS | Container | Services, tasks, node groups |
| Lambda | Serverless | Functions, reserved concurrency |
| SQS/SNS | Queue | Queues, topics, dead letter queues |

## Example

```python
from infrasim.scanners import AWSScanner

scanner = AWSScanner(
    profile="production",
    regions=["us-east-1", "us-west-2"]
)
graph = scanner.scan()

# Graph now contains all discovered AWS resources and their dependencies
print(f"Discovered {len(graph.nodes)} resources")
```

## IAM Permissions

The scanning role needs read-only access. Recommended managed policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:Describe*",
        "rds:Describe*",
        "elasticache:Describe*",
        "elasticloadbalancing:Describe*",
        "s3:GetBucketLocation",
        "s3:GetBucketReplication",
        "route53:List*",
        "cloudfront:List*",
        "ecs:Describe*",
        "ecs:List*",
        "eks:Describe*",
        "eks:List*",
        "lambda:List*",
        "sqs:List*",
        "sns:List*"
      ],
      "Resource": "*"
    }
  ]
}
```
