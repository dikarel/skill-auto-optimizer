# Public API Reference

## Overview

The Acme Corp Public API provides programmatic access to user data, resources, and platform operations.

Base URL: `https://api.acmecorp.com/v2`

## Authentication

All API requests must include a valid API key in the `Authorization` header:

```
Authorization: Bearer <api_key>
```

API keys are issued per-account and can be managed in the developer portal.

## Rate Limits

**Standard tier:**
- 1000 requests per hour per API key
- Burst limit: 100 requests per minute
- Concurrent connections: 10

**Enterprise tier:**
- 10,000 requests per hour per API key
- Burst limit: 500 requests per minute
- Concurrent connections: 50

Rate limit headers are returned with every response:
- `X-RateLimit-Limit`: Maximum requests per hour
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Unix timestamp when the window resets

When the rate limit is exceeded, the API returns HTTP 429 with a `Retry-After` header.

## Endpoints

### Users

`GET /users/{user_id}` — Fetch user data
`PUT /users/{user_id}` — Update user data
`DELETE /users/{user_id}` — Delete user account

### Resources

`GET /resources` — List all resources
`POST /resources` — Create a resource
`GET /resources/{id}` — Fetch a resource
`DELETE /resources/{id}` — Delete a resource

## Error Codes

| Code | Meaning |
|---|---|
| 400 | Bad request — malformed JSON or missing required fields |
| 401 | Unauthorized — invalid or missing API key |
| 403 | Forbidden — insufficient permissions |
| 404 | Not found |
| 429 | Too many requests — rate limit exceeded |
| 500 | Internal server error |
