# Reddit Post — r/terraform

---

## Title Options

1. **I built a tool that checks your terraform plan for resilience issues before you apply — curious what you think**

2. **Does anyone else do pre-apply impact analysis? Built an open source tool for this after a bad incident**

3. **Tool: analyze what your `terraform plan` would break before running `terraform apply`**

Recommended: **#1** — question-framed, invites discussion, honest about it being something the author built.

---

## Body Text

Hey r/terraform,

After a painful incident where a `terraform apply` cascaded through our load balancer into a full outage, I built a tool to catch structural resilience problems *before* the apply. It's called FaultRay and I wanted to share it here and get some feedback from people who actually work with Terraform.

**The problem it solves**

`terraform plan` tells you *what* will change. It doesn't tell you *what that change does to your system's failure behavior*. You can see "will destroy aws_lb.main, will create aws_lb.main" and miss that the destroy happens before the create and your app is in the gap for 90 seconds with no load balancer.

FaultRay reads your terraform plan or state, builds a dependency graph, and runs 2,000+ simulation scenarios against it — looking for single points of failure, cascade paths, components whose removal would cause total outage vs. degraded service.

**Concrete example of what it catches**

Say you're refactoring your database tier — consolidating two RDS instances into one (bigger) instance to save costs. Terraform plan shows:

```
- aws_db_instance.replica  (destroy)
+ aws_db_instance.primary  (replace - forces new resource)
```

Looks fine. But FaultRay will flag:

```
CRITICAL: aws_db_instance.primary
  Replicas: 1 → 0 (removed read replica before primary replacement)
  Impact: All read traffic unserved during replacement window (est. 8-12 min)
  Cascade: api_server → postgres_primary (single point of failure introduced)
  Availability ceiling reduced: 4.2 nines → 3.8 nines
```

That's something you can fix before apply — either by reordering resources, adding a `depends_on`, or deciding the downtime window is acceptable and scheduling it properly.

**Workflow**

```bash
# After terraform plan
terraform plan -out=tfplan

# Check what it does to your resilience
faultray tf-plan tfplan

# Or check current state before making changes
faultray tf-import --dir ./terraform --output model.json
faultray simulate -m model.json

# Apply only if you're satisfied
terraform apply
```

**What it doesn't do**

This is simulation against a dependency model, not real fault injection. It won't catch:
- Application bugs that only appear under failure conditions
- Real-world timing and race conditions
- Third-party dependencies you didn't model

For actual chaos testing you still want something like AWS FIS in staging. FaultRay is the pre-apply sanity check, not a replacement for that.

**Installation**

```bash
pip install faultray
faultray demo    # try it against a sample infrastructure
```

GitHub: https://github.com/mattyopon/faultray

Open source, free. BSL 1.1 (converts to Apache 2.0 in 2030 — basically MIT with a 4-year delay on commercial embedding).

---

**Feedback I'm looking for**

1. Is this the right place in the workflow to catch this? Or do you catch these things somewhere else?
2. What terraform resource types do you most commonly have resilience surprises with? (I want to improve the parser coverage)
3. Does the "availability ceiling" concept (mathematically proving your architecture's max uptime) seem useful or confusing?

Happy to answer any questions about how the simulation model works.
