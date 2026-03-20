# HackerNews Show HN Post — FaultRay

## Title Options (ranked by likely HN engagement)

1. **Show HN: FaultRay -- Chaos engineering that simulates 2k failures without breaking anything**
2. **Show HN: FaultRay -- A flight simulator for your infrastructure resilience**
3. **Show HN: FaultRay -- Zero-risk chaos engineering with AI agent hallucination modeling**

---

## Post Body

**URL:** https://github.com/mattyopon/faultray

**Text:**

FaultRay is a chaos engineering tool that simulates 2,000+ failure scenarios against your infrastructure entirely in memory. Nothing in production gets touched.

The key insight: traditional chaos engineering (Gremlin, AWS FIS) injects real faults into real systems. That works if you can afford the risk. Most teams -- especially in regulated industries -- cannot. FaultRay takes a different approach: it builds a dependency graph of your system from YAML, Terraform state, or Prometheus discovery, then exhaustively simulates cascading failures, compound faults, and capacity limits using five simulation engines (cascade, dynamic, ops, what-if, capacity). The novel part is the AI agent failure model -- it simulates hallucination cascades, context overflow, token exhaustion, and prompt injection for LLM-based agent systems. As far as I know, no other tool does this.

Technical details: the core uses NetworkX for dependency graph modeling. The 5-Layer Availability Limit Model computes a mathematical ceiling for your system's uptime by combining hardware MTBF, software failure rates, operational response times, and external SLA products. The Terraform integration is where most users start -- run `faultray tf-check plan.json` in CI to catch resilience regressions before `terraform apply`. It scores before/after states and flags the delta.

Honest limitations: the simulation is only as good as the model you feed it. If your YAML doesn't capture a dependency, FaultRay won't find it. The AI agent hallucination model is based on published failure mode taxonomies, not trained on production incident data. Auto-discovery from Prometheus helps but won't catch everything. The project is BSL-1.1 (converts to Apache 2.0 in 2030).

- GitHub: https://github.com/mattyopon/faultray
- Paper (DOI): https://doi.org/10.5281/zenodo.19139911
- PyPI: https://pypi.org/project/faultray/
- Try it: `pip install faultray && faultray demo`

---

## Likely HN Questions and Prepared Answers

### "How is this different from Chaos Monkey/Gremlin?"

Chaos Monkey and Gremlin inject real faults into running systems. FaultRay never touches production. It builds a mathematical model of your infrastructure and simulates failures in memory. Think of it as the difference between crash-testing a real car vs. running a finite element simulation. Both are useful, but simulation lets you test 2,000+ scenarios including compound failures that would be too dangerous to inject in production. FaultRay is complementary -- use it for pre-deploy validation in CI/CD, use Gremlin for validating that your production systems actually handle faults the way the model predicts.

### "Why not just use a staging environment?"

Staging environments are perpetually out of sync with production. They usually have different instance counts, different data volumes, different traffic patterns. FaultRay works against the actual topology described in your Terraform state or infrastructure definition, so it reasons about your real architecture. It also runs in seconds, not hours, and doesn't require maintaining a parallel environment. That said, FaultRay tests the topology and dependency structure, not application-level bugs. Staging still has its place.

### "How accurate is the simulation vs real failures?"

The simulation models structural resilience: dependency chains, single points of failure, cascade paths, redundancy coverage. It does not model application-level bugs, network latency distributions, or kernel panics. If your infrastructure YAML accurately describes your dependencies and redundancy, the cascade analysis is reliable for identifying structural weaknesses. The 5-Layer Availability Limit Model gives an upper bound, not a guarantee -- real availability will always be lower due to factors the model cannot capture. We are transparent about this: the tool tells you "your architecture cannot exceed X nines" which is a provably correct ceiling, not a prediction of actual uptime.

### "Why BSL-1.1 and not open source?"

BSL-1.1 is source-available. You can read, modify, and use FaultRay for any purpose except offering it as a competing managed service. It automatically converts to Apache 2.0 on 2030-03-17, so it becomes fully open source by that date. The reasoning: building and maintaining a tool with five simulation engines, Terraform integration, compliance reporting, and AI agent modeling requires sustained investment. BSL lets us keep the code open and readable while maintaining a path to commercial sustainability. For most users -- running it internally, in CI/CD, on your own infrastructure -- the license has zero practical restrictions.

### "Is the AI agent hallucination model validated?"

The AI agent failure model is based on published taxonomies of LLM failure modes (hallucination, context overflow, tool failure, agent loops, prompt injection, rate limiting, token exhaustion). The model simulates what happens to your system when these failures occur -- e.g., if the LLM endpoint goes down, does the agent fail gracefully or does it serve cached/hallucinated responses? It does not predict the probability of hallucinations from a specific model. It models the infrastructure-level consequences of AI-specific failure modes. This is useful for answering questions like "what is our blast radius if Claude's API returns errors for 10 minutes?" but it is not a hallucination detector. The distinction matters and we should be clearer about it in the docs.
