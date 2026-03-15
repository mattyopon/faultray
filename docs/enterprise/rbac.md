# RBAC (Role-Based Access Control)

FaultZero supports role-based access control for multi-team environments, controlling who can view models, run simulations, and modify configurations.

## Overview

RBAC in FaultZero follows a role-permission model where users are assigned roles that grant specific permissions across resources.

## Roles

### Built-in Roles

| Role | Description | Permissions |
|------|-------------|-------------|
| `admin` | Full system access | All operations |
| `engineer` | Infrastructure team member | Create/edit models, run simulations, view reports |
| `viewer` | Read-only access | View models, view reports |
| `ci-bot` | CI/CD service account | Run simulations, read models |
| `auditor` | Compliance reviewer | View reports, export compliance data |

### Custom Roles

Define custom roles in the configuration:

```yaml
rbac:
  roles:
    sre-lead:
      permissions:
        - models:read
        - models:write
        - simulations:run
        - reports:read
        - reports:export
        - settings:read

    junior-engineer:
      permissions:
        - models:read
        - simulations:run
        - reports:read
```

## Permissions

| Permission | Description |
|-----------|-------------|
| `models:read` | View infrastructure models |
| `models:write` | Create and edit models |
| `models:delete` | Delete models |
| `simulations:run` | Execute simulations |
| `simulations:read` | View simulation results |
| `reports:read` | View reports |
| `reports:export` | Export reports (PDF, JSON) |
| `settings:read` | View system settings |
| `settings:write` | Modify system settings |
| `users:manage` | Manage user accounts and roles |

## Configuration

### API Key-based access

```bash
# Create an API key with a specific role
faultzero auth create-key --role engineer --name "CI Pipeline"

# Output: API key with assigned permissions
```

### OAuth/OIDC integration

```yaml
auth:
  provider: oidc
  issuer: https://auth.example.com
  client_id: faultzero-app
  role_mapping:
    "admin-group": admin
    "sre-team": engineer
    "security-team": auditor
```

## Usage Example

```python
from infrasim.auth import RBACManager

rbac = RBACManager()

# Check permissions
if rbac.has_permission(user, "simulations:run"):
    engine.simulate()
else:
    raise PermissionError("Insufficient permissions to run simulations")
```

## Audit Logging

All RBAC-controlled actions are logged with:

- Timestamp
- User identity
- Action performed
- Resource accessed
- Result (allowed/denied)

```bash
faultzero auth audit-log --last 24h
```
