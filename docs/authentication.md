# Authentication and Authorization

The Authentication and Authorization subsystem is responsible for:

- User identity management
- Access control
- Contest permissions
- Administrative operations
- API security

The system should be simple in the first implementation while remaining extensible for future integrations.

---

# Design Goals

The authentication system must support:

- Login
- Logout
- JWT-based authentication
- Role-based access control
- Contest participation permissions
- Administrative permissions

Future versions should support:

- OAuth
- University authentication systems
- Single Sign-On (SSO)
- Multi-factor authentication

---

# Authentication Architecture

The recommended architecture is:

```text
Client
    ↓
Login Request
    ↓
Authentication Service
    ↓
JWT Token
    ↓
Protected API Access
```

The API layer validates tokens and extracts user information.

---

# User Identity

Each user must have:

```python
class User:

    user_id: str

    username: str

    email: str

    password_hash: str

    role: UserRole

    is_active: bool
```

Passwords must never be stored in plaintext.

---

# Password Storage

Passwords must be stored using secure hashing.

Recommended:

```text
bcrypt
```

or

```text
argon2
```

Never store:

```text
raw passwords
```

Never store:

```text
encrypted passwords
```

Store only hashes.

---

# User Creation

EPIC uses a closed registration model: only administrators can create user accounts. Self-service registration is not supported.

Endpoint:

```http
POST /api/v1/users
```

Requires `ADMINISTRATOR` role.

Required information:

```json
{
  "username": "student1",
  "email": "student@example.com",
  "password": "..."
}
```

New accounts are assigned the `PARTICIPANT` role by default. Administrators may specify a different role at creation time.

---

# Login

Users authenticate using credentials.

Endpoint:

```http
POST /api/v1/auth/login
```

Request:

```json
{
  "username": "student1",
  "password": "..."
}
```

Response:

```json
{
  "access_token": "...",
  "token_type": "bearer"
}
```

---

# JWT Tokens

EPIC should use JWT access tokens.

Example payload:

```json
{
  "sub": "user_id",
  "username": "student1",
  "role": "PARTICIPANT",
  "exp": 1700000000
}
```

---

# Token Expiration

Access tokens should expire.

Recommended:

```text
1 hour
```

Refresh tokens may be added later.

---

# Current User

Authenticated users should be retrievable.

Endpoint:

```http
GET /api/v1/auth/me
```

Example response:

```json
{
  "user_id": "123",
  "username": "student1",
  "role": "PARTICIPANT"
}
```

---

# Roles

Supported roles:

```text
ADMINISTRATOR   ← full platform management (users, system settings)
ORGANIZER       ← creates and manages own contests
PARTICIPANT     ← registers for contests, collects data, submits predictions
```

Future roles (Phase 4+):

```text
EXPERT          ← registers new digital twin and sensor plugins at runtime
```

The role names are intentionally domain-independent. ORGANIZER can be a professor,
researcher, or company. PARTICIPANT can be a student, engineer, or external competitor.

---

# Role-Based Access Control

Authorization is based on roles.

## PARTICIPANT can:

- Register for contests (SCHEDULED or ACTIVE)
- Connect to contest WebSocket stream and collect data client-side
- Submit predictions (with temporal integrity anchor)
- View own registrations, submissions, and scores

## ORGANIZER can:

- Create contests
- Manage own contests through full lifecycle (DRAFT → ACTIVE → CLOSED)
- Extend deadlines on own contests
- View all submissions to own contests (for evaluation and grading)
- Cannot modify contests created by other organizers
- Cannot manage users

## ADMINISTRATOR can:

- Everything an ORGANIZER can do, across all contests
- Manage all users (create, deactivate, change roles)
- Inspect all submissions and scores platform-wide
- Override any contest configuration

---

# Protected Endpoints

Contest management endpoints require ORGANIZER or ADMINISTRATOR role.
User management endpoints require ADMINISTRATOR role.

Examples:

```http
POST /api/v1/contests        ← ORGANIZER or ADMINISTRATOR
PATCH /api/v1/contests/{id}  ← ORGANIZER (own contest) or ADMINISTRATOR
GET  /api/v1/users           ← ADMINISTRATOR only
POST /api/v1/users           ← ADMINISTRATOR only
```

---

# Contest Access Control

A participant must satisfy:

```text
Authenticated
```

and

```text
Registered for Contest
```

before submitting solutions.

---

# Registration Validation

Submission workflow:

```text
User
    ↓
Contest Registration
    ↓
Submission Allowed
```

Unregistered users must be rejected.

---

# Authorization Examples

## Allowed

```text
Participant submits solution
to registered contest.
```

---

## Rejected

```text
Participant attempts
to modify contest settings.
```

---

# Contest Ownership

Every contest should track its creator.

Example:

```python
contest.created_by
```

This allows future ownership-based permissions.

---

# API Security

Protected endpoints must require:

```http
Authorization: Bearer <token>
```

Example:

```http
GET /api/v1/contests

Authorization: Bearer eyJ...
```

---

# Public Endpoints

Examples:

```http
POST /api/v1/auth/login
```

No authentication required.

`POST /api/v1/users` requires ADMINISTRATOR authentication (see [User Creation](#user-creation)).

---

# Rate Limiting

Future versions should support:

- Login rate limiting
- Submission rate limiting
- API rate limiting

This helps prevent abuse.

---

# Audit Logging

The system should log:

- User creation
- Login events
- Contest creation
- Contest updates
- Submissions
- Administrative actions

Audit logs are useful for:

- Security
- Research reproducibility
- Contest management

---

# Session Revocation

Future versions may support:

```text
Logout
```

and

```text
Token revocation
```

for improved security.

---

# OAuth Integration

Future versions should support:

```text
Google OAuth
GitHub OAuth
University OAuth
```

without changing application logic.

---

# Single Sign-On

Future integration targets:

```text
SAML
OpenID Connect
University Identity Providers
```

This is particularly useful for academic deployments.

---

# Privacy Requirements

The platform should store only the information necessary to:

- Identify users
- Manage contests
- Evaluate submissions

Personal information should be minimized.

---

# Authentication Flow

Typical workflow:

```text
Admin creates account
    ↓
Login
    ↓
Receive JWT
    ↓
Join Contest
    ↓
Connect to WebSocket stream
    ↓
Collect data client-side
    ↓
Submit Solution
    ↓
View Leaderboard
```

---

# Future Team Support

Future versions may introduce:

```python
Team

TeamMembership
```

allowing team-based competitions.

The authentication architecture should not prevent this extension.

---

# Design Requirement

Authentication and authorization must remain independent from:

- Digital twins
- Sensors
- Fault models
- Scoring metrics

The security subsystem should operate entirely at the platform level.

This guarantees that new domains can be added without modifying authentication logic.