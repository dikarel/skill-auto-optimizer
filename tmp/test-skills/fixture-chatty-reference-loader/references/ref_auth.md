# Authentication Service Reference

## Overview

The Acme Corp Authentication Service handles identity verification, session management, and authorization for all platform services. It is built on OAuth 2.0 and OpenID Connect standards.

## OAuth 2.0 Flows

### Authorization Code Flow (Web Applications)

1. Redirect user to `/oauth/authorize` with `response_type=code`, `client_id`, `redirect_uri`, `scope`, and `state`
2. User authenticates and grants permission
3. Server redirects to `redirect_uri` with `code` and `state`
4. Exchange `code` for tokens at `/oauth/token` using `grant_type=authorization_code`
5. Server returns `access_token`, `refresh_token`, and `id_token`

### Client Credentials Flow (Service-to-Service)

1. POST to `/oauth/token` with `grant_type=client_credentials`, `client_id`, `client_secret`, and `scope`
2. Server returns `access_token` (no refresh token)

### Device Authorization Flow (CLI / IoT)

1. POST to `/oauth/device/code` with `client_id` and `scope`
2. Display `user_code` to user, poll `/oauth/token` with `grant_type=device_code`
3. Server returns tokens once user completes authorization

## Token Specifications

| Token Type | Lifetime | Rotation | Storage |
|---|---|---|---|
| Access Token | 1 hour | On refresh | Memory only (never disk) |
| Refresh Token | 30 days | Single-use | Secure, encrypted storage |
| ID Token | 1 hour | On refresh | Memory only |

## Scopes

| Scope | Description |
|---|---|
| `openid` | Required for OIDC; returns `id_token` |
| `profile` | Name, picture, locale |
| `email` | Email address and verification status |
| `read:resources` | Read-only access to user resources |
| `write:resources` | Create and update resources |
| `admin` | Full administrative access |

## Session Management

- Sessions are server-side; clients hold only tokens
- Session timeout: 24 hours of inactivity
- Maximum session duration: 7 days regardless of activity
- Forced logout propagates to all active sessions for that user

## Permission Model

Permissions follow RBAC (Role-Based Access Control):

| Role | Permissions |
|---|---|
| `viewer` | read:resources |
| `editor` | read:resources, write:resources |
| `admin` | read:resources, write:resources, admin |

Roles are assigned per-workspace and can be scoped to specific resource groups.

## Token Validation

Validate tokens at the `/oauth/introspect` endpoint or use the JWKS endpoint at `/oauth/jwks` to verify signatures locally. Tokens use RS256 signing.

## MFA

Supported MFA methods:
- TOTP (Google Authenticator, Authy)
- WebAuthn / Passkeys
- SMS OTP (deprecated; not recommended for new integrations)
- Hardware keys (FIDO2)

## Security Considerations

- Never log access tokens or refresh tokens
- Rotate secrets immediately if compromised
- Use PKCE for all public clients (mobile, SPA)
- Token binding is available for high-security deployments
