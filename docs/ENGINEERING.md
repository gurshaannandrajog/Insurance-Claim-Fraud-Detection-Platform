# Engineering decisions (and how to explain them)

Each section answers a question you are likely to be asked in a viva or an interview, and points to the code.

## Why Django for the main backend?
The domain is relational and rule-heavy: users, vehicles, policies, claims, documents, appeals and an audit trail.
Django provides a mature ORM with migrations, transactions and row locking (`select_for_update`), a battle-tested
authentication system (salted password hashing, sessions, CSRF, password-reset tokens), and Django REST Framework
for serializers, permissions and pagination. That lets the effort go into the business rules rather than plumbing.

## Why a separate Flask service for fraud detection?
- **Separation of concerns.** Scoring is a different kind of problem from transaction processing. It changes on a different schedule (re-tuning weights, training models) and may need different libraries (scikit-learn, XGBoost) and resources.
- **Stateless and safe.** The service never touches the database. Django gathers the facts (`apps/fraud/features.py`) and sends a JSON payload, and Flask returns a score. The fraud service therefore cannot leak or corrupt data, and can be scaled or replaced on its own.
- **Contract-first.** The JSON request and response is the only coupling, and it is validated on both sides (`fraud_service/validation.py`, `apps/fraud/client.py`).
- **Lightweight.** Flask is enough for a single scoring endpoint.

## How does Django talk to Flask, and what if Flask is down?
`apps/fraud/client.py` sends `POST /api/v1/assess` with a shared-secret header (`X-API-Key`, compared in constant time)
and a timeout of 10 seconds (REQ-PER-003). The call is made **outside** any database transaction, so row locks are never
held while waiting on the network. If the service is unreachable, a `FAILED` assessment is stored with the error, the
claim continues normally (submission is never blocked), and approval is refused until an adjuster re-runs the
assessment. This is graceful degradation: the critical path keeps working, and the control (no decision without a
risk check) is still enforced.

## Rule-based scoring, and how to swap in machine learning
`fraud_service/scoring/rules.py` has 16 small, readable rules. Each returns a `Factor(code, category, description, weight)`.
The score is the sum of the weights, capped at 100, so every point is explainable to an adjuster (REQ-FRD-004). The
bands are 0–29 Low, 30–59 Medium and 60–100 High. Django re-derives the band from the score rather than trusting the
service.

To use machine learning later, implement `RiskScorer.score(features)` in a new class (load a trained model, convert
its probability to 0–100, and turn SHAP or feature-importance values into `Factor`s). Register it in
`scoring/registry.py` and set `FRAUD_ENGINE=ml-v1`. Django, the API contract and the database stay unchanged. Every
stored assessment records which `engine` produced it, and the exact `request_payload`, which can later become training data.

A score never rejects a claim (REQ-FRD-007). High risk moves the claim to *Fraud Review* and opens an SIU
investigation, and the human decision stays with the adjuster.

## Why MySQL?
The SRS requires it, and the data is strongly relational with integrity rules. InnoDB provides ACID transactions,
foreign keys, row-level locks and (on MySQL 8.0.16+) CHECK constraints. Constraints enforced **by the database**
include `approved_amount ≤ requested_amount`, `cumulative ≤ IDV`, a rejection always having a reason, document size
≤ 10 MB, and unique registration, engine, chassis, policy and claim numbers.

One limitation: MySQL has no partial unique index, so "one live policy per vehicle" cannot be a pure unique
constraint. It is enforced in the service layer while holding a `SELECT … FOR UPDATE` lock on the vehicle row, which
serialises two administrators approving requests for the same vehicle at the same moment.

## Normalisation
The schema is in 3NF. A claim stores only `policy_id`; the customer and vehicle are reached through the policy, so a
claim can never point at one customer's policy and another customer's vehicle. There are two deliberate, documented
exceptions:
1. **Policy snapshot** (`plan_name`, `premium_rate_percent`, `premium_amount`): a copy of the plan at sale time. This preserves the contract, which is what REQ-POL-015 asks for.
2. **`Claim.current_risk_score / current_risk_level`**: a copy of the latest assessment, so queues and reports can filter on an indexed column. The full history stays in `FraudAssessment`.

## Entity relationships
See `docs/ANALYSIS.md §3`. Every history-bearing relationship uses `on_delete=PROTECT`, so the database refuses to
delete a vehicle that has policies, a policy that has claims, or a claim that has documents (REQ-VEH-010, REQ-SAF-002).

## REST API design
The API is resource-oriented (`/claims/`, `/policies/`, …). State changes are explicit **actions**
(`POST /claims/{id}/approve/`) rather than `PATCH {"status": "APPROVED"}`, because each transition has its own
inputs, preconditions and side effects. Errors use one envelope with machine-readable codes and correct HTTP statuses
(400 validation, 401 not signed in, 403 forbidden, 404 not found or not yours, 409 conflicting state, 423 locked).

## Authentication vs authorisation
- **Authentication** answers *who are you?*: email and password, verified email, lockout after 4 failures, server-side sessions.
- **Authorisation** answers *what may you do?*, at two levels:
  - **Role permission classes** (`apps/accounts/permissions.py`): may this role call this endpoint at all? (403)
  - **Object scoping** (`apps/claims/selectors.claims_visible_to`, scoped querysets): may this user see this particular record? (404). This is what stops **IDOR**: changing `/claims/12` to `/claims/13` returns 404.
- The frontend hides what a user cannot do, but that is only for usability. Every rule is enforced by the API, and the tests call the API directly.

## Why sessions instead of JWT?
The browser and API share one origin (the Vite proxy in development, or a reverse proxy in production). An HttpOnly
session cookie cannot be read by JavaScript, so an XSS bug cannot steal it. Sessions can be revoked instantly on the
server (logout, deactivation, inactivity timeout), and CSRF is handled by Django's standard token. Tokens kept in
`localStorage` give up both of those properties.

## Password storage
Passwords are stored with PBKDF2-SHA256 using Django's current iteration count (over 1,000,000) and a per-user random
salt; plain text is never stored. Login runs a dummy hash for unknown emails to reduce timing differences, and always
returns the same "Invalid email or password" message.

The deliberate slowness is visible in the load test: about 0.4 s per login. That is the point, because it makes
offline brute-forcing expensive.

## Session management
- 30-minute **inactivity** timeout is enforced by `InactivityTimeoutMiddleware` on the server.
- The notification badge polls with `X-Background-Poll: 1`, which does not count as activity, so a forgotten tab still times out.
- The session id is rotated at login, and the cookie is HttpOnly, SameSite=Lax, and Secure when HTTPS is enabled.

## File validation
1. The extension must be `pdf`, `jpg` or `jpeg`.
2. The size must be between 1 byte and 10 MB (checked by the application and by a database CHECK).
3. The **content signature** must match: `%PDF-` or `FF D8 FF`. A renamed `.exe` fails here.

Files are saved under random names (a UUID) in a directory that is never served statically. Every download goes
through an access check and is sent with `nosniff` and `no-store` headers. A SHA-256 hash of each file lets the fraud
engine detect identical evidence reused across different claims.

## The claim state machine
`apps/claims/workflow.py` holds a single `TRANSITIONS` table, and every status change goes through `transition()`,
which:
1. rejects an illegal move with 409 `invalid_status_transition`;
2. writes a `ClaimStatusHistory` row (from, to, actor, reason, internal flag);
3. writes an `AuditLog` row.

No other code assigns `claim.status`. Services add each transition's own preconditions. For example, approval needs
verified documents, a completed fraud assessment and no open investigation.

## Database transactions
`approve_claim` is a single `transaction.atomic()` that locks the claim and policy rows and updates the claim, the
approved amount, the policy's cumulative amount and status, the status history, the audit log and the notification.
If any step fails, everything rolls back; `test_approval_rolls_back_completely_on_failure` proves this by making the
notification step throw. Emails are sent with `transaction.on_commit`, so a rolled-back approval can never send an
"approved" email.

## Error handling
`apps/core/exceptions.py` maps domain errors (`BusinessRuleError`, `ConflictError`, `InvalidTransitionError`), DRF
errors, Django validation errors and database errors to the one error envelope. Unexpected exceptions are logged with
a stack trace on the server, and the user gets a generic message. In the frontend, every page has loading, empty and
error states, and the API client converts any failure into a readable message.

## Audit logging
`AuditLog` is append-only: there is no update or delete endpoint. Each row records the actor (with an email snapshot
that survives account anonymisation), role, action, entity, metadata and IP address. Over 50 action types are covered,
including logins, failed logins, lockouts, every claim transition, document decisions, fraud assessments, SIU
activity, appeals, policy changes and report exports.

## Automated testing
- **104 Django tests on MySQL**, covering authentication, lockout, timeout, reset, RBAC matrix, IDOR, policy rules, claim lifecycle, 30-minute rule, duplicates, transactions, documents, fraud privacy, SIU, appeals, reports and exports.
- **13 Flask tests**: scoring rules, bands, API contract, authentication and validation.
- **Django ↔ Flask integration tests**: the real Flask app is driven through its test client.
- **Browser end-to-end test** of the whole SRS scenario with Playwright, plus a **load check** for the performance requirements.

## Security checklist
CSRF on every state-changing request (including login), HttpOnly cookies, hashed passwords, lockout and rate
limiting, ORM-only queries (no raw SQL, so no SQL injection), React output escaping (no `dangerouslySetInnerHTML`), IDOR
protection, file validation, fraud data hidden from customers, secrets in `.env`, `X-Frame-Options: DENY`, `nosniff`,
and an HTTPS switch.

## Scalability
The API is stateless apart from database sessions, so it can be scaled horizontally behind a load balancer (sessions
could move to Redis). The fraud service scales independently. Lists are paginated and indexed. The next steps would
be: run Gunicorn or Waitress instead of `runserver`, move documents to object storage (S3) behind the same access
check, move emails and fraud scoring to a task queue (Celery), and use Redis for caching and rate limits.
