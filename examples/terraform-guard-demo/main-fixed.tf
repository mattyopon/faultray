# terraform-guard-demo/main-fixed.tf
#
# The same infrastructure as main.tf with all resilience issues resolved.
# Run `faultray tf-check` on the plan output to see a clean report.
#
# Fixes applied:
#   [1] ECS desired_count = 3   → multi-AZ task distribution, tolerates 1 failure
#   [2] RDS multi_az = true     → synchronous standby in a separate AZ
#   [3] Redis replication group → primary + 1 replica, auto-failover enabled
#   [4] Bastion SG restricted   → SSH only from a known management CIDR

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  default = "us-east-1"
}

variable "app_name" {
  default = "myapp"
}

variable "db_password" {
  description = "RDS master password"
  sensitive   = true
}

# Replace "203.0.113.0/24" with your actual management IP range.
variable "management_cidr" {
  description = "CIDR allowed to reach the bastion over SSH"
  default     = "203.0.113.0/24"
}

# ─────────────────────────────────────────────
# VPC
# ─────────────────────────────────────────────

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true

  tags = { Name = "${var.app_name}-vpc" }
}

resource "aws_subnet" "public_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "${var.aws_region}a"

  tags = { Name = "${var.app_name}-public-a" }
}

resource "aws_subnet" "public_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "${var.aws_region}b"

  tags = { Name = "${var.app_name}-public-b" }
}

resource "aws_subnet" "private_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.10.0/24"
  availability_zone = "${var.aws_region}a"

  tags = { Name = "${var.app_name}-private-a" }
}

resource "aws_subnet" "private_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = "${var.aws_region}b"

  tags = { Name = "${var.app_name}-private-b" }
}

# ─────────────────────────────────────────────
# Security Groups
# ─────────────────────────────────────────────

# FIX [4]: SSH restricted to a known management CIDR instead of 0.0.0.0/0
resource "aws_security_group" "bastion" {
  name        = "${var.app_name}-bastion"
  description = "Bastion host — SSH from management network only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "SSH from management network"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.management_cidr] # FIX: locked to known range
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.app_name}-bastion-sg" }
}

resource "aws_security_group" "alb" {
  name        = "${var.app_name}-alb"
  description = "Application Load Balancer"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.app_name}-alb-sg" }
}

resource "aws_security_group" "app" {
  name        = "${var.app_name}-app"
  description = "ECS tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.app_name}-app-sg" }
}

# ─────────────────────────────────────────────
# Application Load Balancer
# ─────────────────────────────────────────────

resource "aws_lb" "main" {
  name               = "${var.app_name}-alb"
  load_balancer_type = "application"
  subnets            = [aws_subnet.public_a.id, aws_subnet.public_b.id]
  security_groups    = [aws_security_group.alb.id]

  tags = { Name = "${var.app_name}-alb" }
}

resource "aws_lb_target_group" "app" {
  name        = "${var.app_name}-tg"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.main.arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

resource "aws_acm_certificate" "main" {
  domain_name       = "${var.app_name}.example.com"
  validation_method = "DNS"
}

# ─────────────────────────────────────────────
# ECS Cluster + Service
# ─────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = "${var.app_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "app" {
  family                   = "${var.app_name}-task"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([
    {
      name      = "app"
      image     = "nginx:latest"
      essential = true
      portMappings = [
        { containerPort = 8080, hostPort = 8080, protocol = "tcp" }
      ]
      environment = [
        { name = "REDIS_HOST", value = aws_elasticache_replication_group.cache.primary_endpoint_address },
        { name = "DB_HOST",    value = aws_db_instance.main.address }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.app_name}"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "app"
        }
      }
    }
  ])
}

# FIX [1]: desired_count = 3 distributes tasks across AZs.
# Fargate places tasks in different AZs when multiple subnets are provided.
# The service can lose an entire AZ and keep serving traffic.
resource "aws_ecs_service" "app" {
  name            = "${var.app_name}-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 3 # FIX: 3 tasks across 2 AZs; 1 task loss does not cause downtime

  launch_type = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.private_a.id, aws_subnet.private_b.id]
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = 8080
  }

  # Deployment circuit breaker prevents a bad deploy from taking down all tasks.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_lb_listener.https]
}

resource "aws_iam_role" "ecs_execution" {
  name = "${var.app_name}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ─────────────────────────────────────────────
# RDS (PostgreSQL)
# ─────────────────────────────────────────────

resource "aws_db_subnet_group" "main" {
  name       = "${var.app_name}-db-subnet"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

# FIX [2]: multi_az = true provisions a synchronous standby replica in a second AZ.
# RDS automatically fails over to the standby (typically < 2 minutes) without data loss.
resource "aws_db_instance" "main" {
  identifier        = "${var.app_name}-db"
  engine            = "postgres"
  engine_version    = "16.2"
  instance_class    = "db.t3.medium"
  allocated_storage = 100
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "appdb"
  username = "appuser"
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.app.id]

  multi_az            = true # FIX: synchronous standby in a second AZ
  skip_final_snapshot = false
  deletion_protection = true

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  tags = { Name = "${var.app_name}-db" }
}

# ─────────────────────────────────────────────
# ElastiCache (Redis) — Replication Group
# ─────────────────────────────────────────────

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.app_name}-cache-subnet"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

# FIX [3]: Replace the single-node cluster with a replication group.
# - 1 primary + 1 replica across two AZs
# - automatic_failover_enabled = true promotes the replica on primary failure
# - multi_az_enabled = true ensures the replica is in a different AZ
resource "aws_elasticache_replication_group" "cache" {
  replication_group_id = "${var.app_name}-cache"
  description          = "Redis replication group with automatic failover"

  node_type            = "cache.t3.micro"
  num_cache_clusters   = 2 # FIX: 1 primary + 1 replica
  parameter_group_name = "default.redis7"
  engine_version       = "7.1"
  port                 = 6379

  subnet_group_name          = aws_elasticache_subnet_group.main.name
  automatic_failover_enabled = true # FIX: auto-promote replica on primary failure
  multi_az_enabled           = true # FIX: replica placed in a separate AZ

  at_rest_encryption_enabled  = true
  transit_encryption_enabled  = true

  tags = { Name = "${var.app_name}-cache" }
}

# ─────────────────────────────────────────────
# Outputs
# ─────────────────────────────────────────────

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "db_endpoint" {
  value     = aws_db_instance.main.endpoint
  sensitive = true
}

output "cache_primary_endpoint" {
  value = aws_elasticache_replication_group.cache.primary_endpoint_address
}
