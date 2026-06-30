# DORA Resilience Scenarios — Cloud-Native EU Payment / E-Money Institution

Five sanitized, illustrative topology scenarios modelling DORA-relevant ICT
disruptions for a cloud-native EU **payment institution (PI) / e-money
institution (EMI)** processing card and SEPA/instant payments. They exist to
exercise FaultRay against realistic payment-domain failure modes and to seed a
**DORA pre-audit resilience evidence pack** for a single critical service.

These are **synthetic, decision-support** topologies built from no production
data and no PII. They are not legal advice, not a DORA certification, and do
not replace threat-led penetration testing (TLPT) or an auditor's sign-off.

## Scenarios → DORA articles

| # | File | Failure modelled | DORA articles evidenced |
| --- | --- | --- | --- |
| 1 | `01-cloud-az-region-outage.yaml` | Loss of a primary cloud Availability Zone with cross-region DR cutover | **Art. 11** (response & recovery), **Art. 24** (resilience testing) |
| 2 | `02-payment-processor-thirdparty-outage.yaml` | Required external card processor / scheme connector outage; third-party concentration | **Art. 28** (ICT third-party risk), **Art. 30** (key contractual provisions) |
| 3 | `03-ledger-db-failover-restore.yaml` | Ledger Postgres primary loss with replica failover and backup/restore path | **Art. 12** (backup & restoration), **Art. 11** (response & recovery) |
| 4 | `04-api-gateway-idp-saturation.yaml` | API gateway + external identity provider (IdP) saturation and auth-path cascade | **Art. 24** (resilience testing), **Art. 11** (response & recovery) |
| 5 | `05-payment-core-ledger-partition.yaml` | Network partition between payment-core and the ledger/data tier (split-brain risk) | **Art. 11**, **Art. 12**, **Art. 24** |

## How to use

Run a chaos simulation against any scenario:

```bash
faultray simulate --model examples/dora/01-cloud-az-region-outage.yaml
```

Or generate a per-service DORA pre-audit evidence pack (Markdown, plus optional
print-ready HTML with `--pdf`):

```bash
# Scenario 2 — evidence pack for the external payment processor dependency
faultray report dora examples/dora/02-payment-processor-thirdparty-outage.yaml \
  --service processor-api --company "Your Institution" \
  --rto 2h --rpo 15m --output evidence-pack.md
```

Suggested `--service` targets per scenario:

| # | Suggested critical service (`--service`) |
| --- | --- |
| 1 | `ledger-db` (or `dr-ledger-db` for the DR replica) |
| 2 | `processor-api` (external card processor) |
| 3 | `ledger-primary` (or `restore-db` for the restore path) |
| 4 | `external-idp` (or `api-gateway`) |
| 5 | `ledger-primary` (or `payment-core`) |

External ICT third parties are modelled as `external_api` components (e.g.
`processor-api`, `scheme-api`, `kyc-api`, `external-idp`, `card-scheme`,
`sepa-processor`) so the evidence pack's Article 28/30 third-party and
concentration analysis surfaces them.

## Booking the full engagement

These scenarios illustrate the kind of evidence the fixed-scope **DORA
Resilience Evidence Sprint** produces for one real critical service (5 business
days, sanitized data, no production access, no PII; $2,500, 50% upfront). See
[`../../docs/sales/dora-evidence-pack-template.md`](../../docs/sales/dora-evidence-pack-template.md)
and book a 20-minute scoping call: https://faultray.com/evidence-sprint
