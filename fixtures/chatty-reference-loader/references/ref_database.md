# Database Reference

## Overview

Acme Corp uses PostgreSQL 15 as its primary database. All production databases run in a multi-AZ RDS cluster on AWS us-east-1.

## Connection Details

| Environment | Host | Port | Max Connections |
|---|---|---|---|
| Production | db.prod.acmecorp.internal | 5432 | 500 |
| Staging | db.staging.acmecorp.internal | 5432 | 100 |
| Development | localhost | 5432 | 50 |

All connections must use SSL. Connection strings use the format:
`postgresql://user:password@host:5432/acme_db?sslmode=require`

## Connection Pooling

PgBouncer is deployed in front of all production databases:
- Pool mode: transaction
- Max client connections: 10,000
- Max server connections: 500
- Connection timeout: 30 seconds

## Schema Overview

### Core Tables

**`users`**
- `id` UUID PRIMARY KEY
- `email` VARCHAR(255) UNIQUE NOT NULL
- `created_at` TIMESTAMPTZ
- `updated_at` TIMESTAMPTZ
- `deleted_at` TIMESTAMPTZ (soft delete)
- `status` ENUM('active', 'suspended', 'deleted')

**`accounts`**
- `id` UUID PRIMARY KEY
- `name` VARCHAR(255) NOT NULL
- `plan_id` UUID REFERENCES plans(id)
- `created_at` TIMESTAMPTZ
- `owner_user_id` UUID REFERENCES users(id)

**`resources`**
- `id` UUID PRIMARY KEY
- `account_id` UUID REFERENCES accounts(id)
- `type` VARCHAR(100)
- `data` JSONB
- `created_at` TIMESTAMPTZ
- `updated_at` TIMESTAMPTZ

**`api_keys`**
- `id` UUID PRIMARY KEY
- `account_id` UUID REFERENCES accounts(id)
- `key_hash` VARCHAR(64) NOT NULL (SHA-256 of raw key)
- `name` VARCHAR(255)
- `last_used_at` TIMESTAMPTZ
- `created_at` TIMESTAMPTZ
- `revoked_at` TIMESTAMPTZ

**`subscriptions`**
- `id` UUID PRIMARY KEY
- `account_id` UUID REFERENCES accounts(id)
- `plan_id` UUID REFERENCES plans(id)
- `status` ENUM('trialing', 'active', 'past_due', 'canceled', 'expired')
- `current_period_start` TIMESTAMPTZ
- `current_period_end` TIMESTAMPTZ
- `trial_end` TIMESTAMPTZ

**`invoices`**
- `id` UUID PRIMARY KEY
- `account_id` UUID REFERENCES accounts(id)
- `amount_cents` INTEGER NOT NULL
- `currency` CHAR(3) DEFAULT 'USD'
- `status` ENUM('draft', 'open', 'paid', 'void', 'uncollectible')
- `due_date` DATE
- `paid_at` TIMESTAMPTZ
- `stripe_invoice_id` VARCHAR(255)

## Indexes

Critical indexes for performance:
- `users(email)` — unique index
- `api_keys(key_hash)` — unique index (lookup by key)
- `resources(account_id, created_at DESC)` — listing resources
- `invoices(account_id, status)` — invoice queries
- `subscriptions(account_id, status)` — active subscription lookup

## Backup and Recovery

- Automated daily snapshots retained for 35 days
- Point-in-time recovery available for last 7 days (WAL-based)
- Cross-region replica in us-west-2 for disaster recovery
- RTO: 4 hours | RPO: 1 hour

## Migrations

All schema changes are managed with Flyway. Migrations must:
1. Be backward-compatible for at least one release
2. Include a rollback script
3. Run in under 5 seconds on production row counts (or use online DDL)
4. Be reviewed by the database team for changes to core tables
