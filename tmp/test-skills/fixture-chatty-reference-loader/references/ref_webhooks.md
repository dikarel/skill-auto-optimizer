# Webhook Service Reference

## Overview

The Acme Corp Webhook Service delivers real-time event notifications to registered endpoints whenever platform events occur. Webhooks use HTTP POST with JSON payloads and HMAC-SHA256 signature verification.

## Registration

Register webhooks via the API or dashboard:

```
POST /webhooks
{
  "url": "https://your-server.com/hooks/acme",
  "events": ["user.created", "subscription.updated", "invoice.paid"],
  "secret": "your_webhook_secret"
}
```

Each webhook registration receives a unique `webhook_id`.

## Event Types

| Event | Description |
|---|---|
| `user.created` | New user account created |
| `user.updated` | User profile updated |
| `user.deleted` | User account deleted |
| `subscription.created` | New subscription started |
| `subscription.updated` | Subscription plan or status changed |
| `subscription.canceled` | Subscription canceled |
| `invoice.created` | Invoice generated |
| `invoice.paid` | Invoice successfully paid |
| `invoice.payment_failed` | Payment attempt failed |
| `resource.created` | New resource created |
| `resource.updated` | Resource updated |
| `resource.deleted` | Resource deleted |
| `api_key.created` | New API key issued |
| `api_key.revoked` | API key revoked |

## Payload Schema

All webhook payloads share a common envelope:

```json
{
  "id": "evt_01HXYZ...",
  "type": "invoice.paid",
  "created": 1710432000,
  "api_version": "2024-01-01",
  "data": {
    "object": { ... }
  }
}
```

The `data.object` field contains the full resource snapshot at the time of the event.

## Signature Verification

Every webhook delivery includes an `X-Acme-Signature-256` header:

```
X-Acme-Signature-256: sha256=abc123...
```

Verification (Python):
```python
import hmac, hashlib

def verify_signature(payload_body: bytes, secret: str, signature_header: str) -> bool:
    expected = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)
```

## Delivery and Retry Policy

- First attempt: immediate (within 5 seconds of event)
- On failure (non-2xx response or timeout): retry with exponential backoff
  - Retry 1: 30 seconds
  - Retry 2: 5 minutes
  - Retry 3: 30 minutes
  - Retry 4: 2 hours
  - Retry 5: 12 hours
  - After 5 failed retries: webhook marked as failed; alert sent to account owner
- Timeout per attempt: 30 seconds
- Delivery order: best-effort (not guaranteed); use event `id` for deduplication

## Best Practices

1. Respond with 2xx within 30 seconds; process asynchronously if needed
2. Validate signatures before processing payloads
3. Implement idempotency using event `id`
4. Expose a `/webhooks/health` endpoint for connectivity testing
5. Use HTTPS with a valid certificate; HTTP not supported in production

## Monitoring

Webhook delivery logs are available in the dashboard for 30 days. The API provides:

```
GET /webhooks/{webhook_id}/deliveries
GET /webhooks/{webhook_id}/deliveries/{delivery_id}/retry
```
