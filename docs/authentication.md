# Authentication and Authorization

> Related: [API Specification](api-specification.md) · [Contest Management](contest-management.md) · [Configuration](configuration.md)

The authentication and authorization subsystem covers user identity management, access control, contest permissions, administrative operations, and API security. It is deliberately simple in the current implementation — username and password, JWT bearer tokens, three roles — while remaining structurally open to the integrations an academic deployment eventually needs: OAuth providers, university identity systems, single sign-on, and multi-factor authentication.

---

# Architecture

The flow is conventional and that is a feature. A client presents credentials to the login endpoint, the authentication service verifies them and issues a JWT access token, and from then on every protected request carries that token in the `Authorization` header. The API layer validates the token on each request and extracts the user identity and role from it; no server-side session state is kept.

```text
Client → Login Request → Authentication Service → JWT Token → Protected API Access
```

---

# User Identity and Password Storage

A user record carries a unique identifier, a username, an email address, a password hash, a role, and a status (`ACTIVE`, `SUSPENDED`, or `DELETED` — deletion is a soft delete that preserves referential integrity for past contests and submissions). The full entity is defined in [Domain Model](domain-model.md).

Passwords are never stored in plaintext, and never stored encrypted either — encryption is reversible, and reversibility is precisely the property a credential store must not have. EPIC stores only bcrypt hashes. Argon2 is an acceptable alternative should the hashing backend ever need to change; nothing in the system depends on the specific algorithm beyond the hashing module itself.

---

# User Registration

There is no open self-registration for participants. EPIC supports three account-creation paths, each matched to a role.

**Organizer self-registration.** Anyone can submit an organizer request through `POST /api/v1/organizer-requests`, with no authentication required. The request enters a PENDING queue that administrators review. On approval, an ORGANIZER account is created automatically — the username is the submitted email address — and the applicant receives an email notification with their login link. On rejection, they receive a notification explaining the outcome.

**Participant invitation.** Organizers invite participants to a specific contest through `POST /api/v1/contests/{contest_id}/invitations`, which requires the ORGANIZER or ADMINISTRATOR role. The platform generates a personal, one-time token for each invited email address and sends an invitation link valid for seven days. The participant follows the link and completes registration through `POST /api/v1/invitations/{token}/accept` — again without prior authentication, since the token itself is the credential. On success the account is created with the PARTICIPANT role, immediately linked to the inviting contest, and a JWT is returned so the participant can start working at once.

**Administrator-created accounts.** Administrators can always create accounts directly through `POST /api/v1/users`. New accounts default to the PARTICIPANT role, but the administrator may specify any role at creation time.

---

# Login and Tokens

Users authenticate with `POST /api/v1/auth/login`, sending their username and password and receiving a bearer token:

```json
{
  "access_token": "...",
  "token_type": "bearer"
}
```

The token is a JWT whose payload identifies the user and their role and carries an expiry:

```json
{
  "sub": "user_id",
  "username": "student1",
  "role": "PARTICIPANT",
  "exp": 1700000000
}
```

Access tokens expire after one hour by default; the lifetime is configurable through `ACCESS_TOKEN_EXPIRE_MINUTES` (see [Configuration](configuration.md)). There are currently no refresh tokens — a client whose token expires simply logs in again — and no server-side revocation, which means a leaked token remains valid until expiry. Refresh tokens and revocation are candidate future additions, as is rate limiting on login, submissions, and the API in general.

The authenticated identity behind a token is retrievable at any time through `GET /api/v1/auth/me`, which returns the user id, username, and role.

---

# Roles

EPIC defines three roles, and their names are intentionally domain-independent: an ORGANIZER can be a professor, a researcher, or a company; a PARTICIPANT can be a student, an engineer, or an external competitor.

The **PARTICIPANT** registers for contests in the SCHEDULED or ACTIVE state, connects to the contest WebSocket stream to collect data client-side, submits predictions once the submission window opens, and views their own registrations, submissions, and scores.

The **ORGANIZER** creates contests and manages their own through the full lifecycle, extends deadlines, and views every submission made to their contests for evaluation and grading. The boundary is ownership: an organizer cannot modify contests created by other organizers, and cannot manage users.

The **ADMINISTRATOR** can do everything an organizer can do across all contests, manages all users (creation, suspension, role changes), inspects all submissions and scores platform-wide, and can override any contest configuration.

A fourth role is anticipated for a later phase: an **EXPERT** role permitted to register new digital twin and sensor plugins at runtime, separating plugin governance from platform administration.

---

# Access Control in Practice

Authorization is enforced per endpoint, based on the role carried in the token. Contest management endpoints (`POST /api/v1/contests`, `PATCH /api/v1/contests/{id}`) require ORGANIZER or ADMINISTRATOR, with the organizer path additionally checking ownership. User management endpoints (`GET /api/v1/users`, `POST /api/v1/users`) are administrator-only. The only fully public endpoints are login, the organizer request form, and invitation acceptance — everything else expects `Authorization: Bearer <token>`.

For contest participation a second condition stacks on top of authentication: a participant must hold an active registration for the specific contest before the platform accepts their submissions. An authenticated but unregistered user is rejected. Contest ownership is tracked through `contest.created_by`, which is what makes the organizer's "own contests only" rule enforceable and leaves room for richer ownership-based permissions later.

So, as a concrete pair of examples: a participant submitting a solution to a contest they are registered for is allowed; the same participant attempting to modify that contest's settings is rejected, because contest modification belongs to the organizer who owns it and to administrators.

---

# Auditability and Privacy

The platform keeps durable records of user creation, login events, contest creation and updates, submissions, and administrative actions. These records serve security review, research reproducibility, and day-to-day contest management equally — an instructor reconstructing what happened during a course competition needs the same trail as a security audit.

On the privacy side, the platform stores only what it needs to identify users, manage contests, and evaluate submissions. Personal information is minimized deliberately: name, email, and an optional phone number collected at registration, nothing more.

---

# Planned Integrations

The roadmap includes OAuth providers (Google, GitHub, university OAuth), and SSO through SAML and OpenID Connect for academic deployments where students already hold institutional identities. Team-based competitions will introduce `Team` and `TeamMembership` entities. The current architecture was shaped so that none of these additions require changes to application logic — they extend the identity layer, not the permission model.

---

# Design Requirement

Authentication and authorization must remain independent from digital twins, sensors, fault models, and scoring metrics. The security subsystem operates entirely at the platform level: no plugin can observe, influence, or depend on it.
