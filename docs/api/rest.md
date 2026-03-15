# REST API

FaultZero provides a REST API for programmatic access to simulation and scoring features.

## Base URL

```
http://localhost:8000/api/v1
```

## Authentication

API requests require a bearer token:

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" http://localhost:8000/api/v1/models
```

## Endpoints

### Models

#### List models

```http
GET /api/v1/models
```

Response:

```json
{
  "models": [
    {
      "id": "abc123",
      "name": "production-infra",
      "created_at": "2025-01-15T10:30:00Z",
      "node_count": 42
    }
  ]
}
```

#### Create model

```http
POST /api/v1/models
Content-Type: application/json

{
  "name": "my-infrastructure",
  "nodes": [...],
  "edges": [...]
}
```

#### Get model

```http
GET /api/v1/models/{model_id}
```

### Simulations

#### Run simulation

```http
POST /api/v1/simulations
Content-Type: application/json

{
  "model_id": "abc123",
  "scenarios": "all",
  "cascade_depth": 5
}
```

Response:

```json
{
  "simulation_id": "sim_456",
  "status": "completed",
  "resilience_score": 78,
  "total_scenarios": 156,
  "passed": 140,
  "failed": 16,
  "critical": 2,
  "warning": 8
}
```

#### Get simulation results

```http
GET /api/v1/simulations/{simulation_id}
```

### Reports

#### Generate report

```http
POST /api/v1/reports
Content-Type: application/json

{
  "simulation_id": "sim_456",
  "format": "html"
}
```

### Health

#### Health check

```http
GET /api/v1/health
```

Response:

```json
{
  "status": "healthy",
  "version": "1.2.0"
}
```

## Error Responses

All errors follow a standard format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Model must contain at least one node",
    "details": {}
  }
}
```

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | `VALIDATION_ERROR` | Invalid request body |
| 401 | `UNAUTHORIZED` | Missing or invalid API key |
| 404 | `NOT_FOUND` | Resource not found |
| 500 | `INTERNAL_ERROR` | Server error |
