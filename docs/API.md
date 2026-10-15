# REST API reference

Base URL: `/api/` (the Vite dev server proxies `/api` to Django on port 8000).

## Conventions

| Topic | Rule |
|---|---|
| Authentication | Server-side session in an HttpOnly cookie (`icp_session`). Call `GET /api/auth/csrf/` once, then send the `csrftoken` cookie value in the `X-CSRFToken` header on every `POST`/`PATCH`. |
| Format | JSON in and out. Uploads use `multipart/form-data`. |
| Lists | Paginated: `{"count", "next", "previous", "results"}`. `?page=` and `?page_size=` (max 100). |
| Errors | Always `{"error": {"code": "...", "message": "...", "fields": {...}}}`. Stack traces are never returned. |
| Not yours | Records another user may not see return **404**, not 403, so their existence is not revealed (IDOR protection). |

### Status codes used

| Code | Meaning in this API |
|---|---|
| 200 / 201 / 204 | OK / created / no content |
| 400 | Validation failed (`validation_error`, or a business code such as `missing_documents`, `reason_required`) |
| 401 | Not signed in (`not_authenticated`), session expired after 30 min of inactivity (`session_expired`), bad credentials (`invalid_credentials`) |
| 403 | Signed in but the role may not do this (`permission_denied`, `adjuster_only`, `not_assigned_adjuster`, `email_not_verified`) |
| 404 | Does not exist, or belongs to someone else |
| 409 | Conflicts with current state: `invalid_status_transition`, `duplicate_claim`, `edit_window_closed`, `vehicle_has_live_policy`, `documents_not_verified`, `investigation_open`, `fraud_assessment_missing`, … |
| 423 | Account locked after 4 failed sign-ins (`account_locked`, with `locked_until`) |
| 429 | Rate limited (login, registration, reset, verification endpoints) |
| 503 | Database unavailable |

Roles: **C** Customer · **A** Claim Adjuster · **S** SIU Investigator · **M** Administrator.

---

## Authentication — `/api/auth/`

| Method & path | Who | Body | Notes |
|---|---|---|---|
| `GET csrf/` | anyone | – | Sets the `csrftoken` cookie |
| `POST register/` | anyone | `email, password, confirm_password, full_name, phone, date_of_birth, address_line, city, state, postal_code` | Creates an unverified customer and emails a verification link. Password policy enforced server-side. |
| `POST verify-email/` | anyone | `token` | Signed, expiring token (48 h) |
| `POST resend-verification/` | anyone | `email` | Always 200 (does not reveal accounts) |
| `POST login/` | anyone | `email, password` | Returns the user. 401 / 423 / 403 as above. Session id rotated on login. |
| `POST logout/` | signed in | – | 204 |
| `GET me/` | signed in | – | Current user with profile |
| `POST password-reset/` | anyone | `email` | Always 200; emails a single-use link |
| `POST password-reset/confirm/` | anyone | `uid, token, new_password` | Also how new staff set their first password |
| `POST change-password/` | signed in | `current_password, new_password` | |

## Profile — `/api/profile/` (C)

| | | |
|---|---|---|
| `GET /` | | Profile |
| `PATCH /` | `full_name, phone, address_line, city, state, postal_code` | `email` and `date_of_birth` are rejected (REQ-CUST-003) |
| `POST delete/` | `password` | 409 `active_claims_exist` while any claim is open |

## Vehicles — `/api/vehicles/`

| | Who | |
|---|---|---|
| `GET /` `?search=` | C (own), A S M | |
| `POST /` | C | Registration / engine / chassis numbers are normalised and unique (409 `duplicate_*`) |
| `GET /{id}/` | C (own), A S M | Includes `is_locked`, `current_policy` |
| `PATCH /{id}/` | C (own) | 409 `vehicle_locked` once linked to a policy or a pending request |
| `DELETE` | – | Not available (405): vehicle history is permanent |

## Plans, policy requests, policies

| | Who | |
|---|---|---|
| `GET /api/policy-plans/` | all | Customers see offered plans only |
| `POST /api/policy-plans/`, `PATCH /{id}/` | M | Affects future policies only |
| `GET /api/policy-requests/` `?status=` | C (own), M | |
| `POST /api/policy-requests/` | C | `vehicle_id, plan_id, requested_idv, notes`. 409 if the vehicle has a live policy or a pending request |
| `POST /api/policy-requests/{id}/withdraw/` | C | |
| `POST /api/policy-requests/{id}/approve/` | M | `start_date?, idv?, decision_note?` → creates an **Active** policy with a unique `POL-YYYY-NNNNNN` |
| `POST /api/policy-requests/{id}/reject/` | M | `reason` |
| `GET /api/policies/` `?status=ACTIVE,PARTIALLY_CLAIMED&vehicle=&search=` | C (own), A S M | Due policies are expired before listing |
| `GET /api/policies/{id}/` | C (own), A S M | |
| `POST /api/policies/{id}/cancel/` | M | `reason`. 409 while claims are open |

## Claims — `/api/claims/`

Filters on `GET /`: `status` (comma-separated), `claim_type`, `policy`, `date_from`, `date_to`, `search`, `ordering`
(`submitted_at`, `requested_amount`, `current_risk_score`, prefix `-` for descending). Staff only: `risk_level`,
`flagged=true`, `assigned=me|none`.

The **response shape depends on the role**. Customers receive a serializer that contains no fraud fields at all,
shows `FRAUD_REVIEW` as `UNDER_REVIEW`, and strips reasons from internal timeline entries. Staff receive customer,
vehicle, policy, documents, `fraud_assessments` (score + indicators), `investigations`, appeals, timeline and the
customer's other claims. Both include `actions`: the operations this user may perform right now, computed on the server.

| Method & path | Who | Body | Result |
|---|---|---|---|
| `POST /` | C | multipart: `vehicle_id, policy_id, claim_type (ACCIDENT/FIRE/THIRD_PARTY), incident_date, incident_time, incident_location, description, requested_amount`, plus parallel lists `document_types[]` and `files[]` (KYC, ADDRESS_PROOF and VEHICLE_REGISTRATION required) | 201, status `SUBMITTED`, fraud assessment run |
| `PATCH /{id}/` | C | any claim field | Only while `SUBMITTED`, within 30 min and before review (409 `edit_window_closed` / `claim_locked_review_started`). Re-runs fraud scoring. |
| `POST /{id}/withdraw/` | C | – | Before review only → `CLOSED` |
| `GET, POST /{id}/documents/` | C (own), A | `document_type, file, replaces?` | Upload or replace a document |
| `POST /{id}/appeal/` | C | multipart `reason` (≥ 20 chars), optional `document_types[]` and `files[]` | Rejected claims, inside the 30-day window, if appeals are still allowed |
| `POST /{id}/accept-decision/` | C | – | Rejected → `CLOSED` |
| `POST /{id}/start-review/` | A | – | `SUBMITTED → UNDER_REVIEW` (assigns the adjuster and ends editing) or `DOCUMENTS_PENDING → UNDER_REVIEW` |
| `POST /{id}/request-documents/` | A | `note` | `→ DOCUMENTS_PENDING`, customer emailed |
| `POST /{id}/escalate/` | A | `reason` | `→ FRAUD_REVIEW`, SIU investigation opened |
| `POST /{id}/approve/` | A (assigned) | `approved_amount, notes?` | Requires `UNDER_REVIEW`, verified mandatory and evidence documents, a completed fraud assessment and no open investigation. Updates the policy's cumulative amount and status in the same transaction. |
| `POST /{id}/reject/` | A (assigned) | `reason, allow_further_appeal?` | `allow_further_appeal` is required once the claim has been appealed; `false` → `PERMANENTLY_REJECTED` |
| `POST /{id}/rerun-fraud/` | A | – | New assessment (kept in history) |

## Appeals — `/api/appeals/`

| | Who | |
|---|---|---|
| `GET /` `?status=PENDING` | C (own), A, S, M | |
| `POST /{id}/decide/` | A | `accept: bool, note, allow_further_appeal?` (required when declining). Accept → claim reopened (`UNDER_REVIEW`) and re-scored. |

## Documents — `/api/documents/`

| | Who | |
|---|---|---|
| `GET /{id}/` | owner C, A, S (flagged claims only) | Metadata and review history |
| `GET /{id}/download/` `?inline=1` | same | File streamed only after the access check. Files are never served as static URLs. |
| `POST /{id}/verify/` | A | Pending → Verified |
| `POST /{id}/reject/` | A | `reason` (required) → customer notified in-app and by email |

Upload rules: extension `pdf/jpg/jpeg`, 1 byte to 10 MB, and content must start with the real PDF/JPEG signature.
Files are stored under random names, with a SHA-256 hash used to detect evidence reused across claims.

## Fraud and investigations

| | Who | |
|---|---|---|
| `GET /api/fraud/assessments/` `?claim=` | A S M (customers get 403) | Every run, with indicators |
| `GET /api/fraud/health/` | A S M | `{fraud_service_available}` |
| `GET /api/investigations/` `?status=OPEN,IN_PROGRESS&mine=true&claim=` | A S M | |
| `POST /api/investigations/{id}/start/` | S | Assign to self |
| `POST /api/investigations/{id}/progress/` | S | `findings?, evidence_notes?, note?` |
| `POST /api/investigations/{id}/complete/` | S | `findings, recommendation (LEGITIMATE/SUSPICIOUS/FRAUDULENT/INCONCLUSIVE), evidence_notes?` → claim returns to `UNDER_REVIEW` for the adjuster's decision. Completed investigations are immutable. |

### Flask fraud service (internal, not exposed to browsers)

`POST http://127.0.0.1:5001/api/v1/assess` with header `X-API-Key`.

```json
{
  "claim":    {"claim_type": "FIRE", "requested_amount": 395000, "incident_date": "2026-10-05", "incident_time": "02:20",
               "submitted_at": "2026-10-06T17:27:00+05:30", "description_length": 48},
  "policy":   {"start_date": "2026-09-26", "end_date": "2027-09-25", "idv": 420000, "cumulative_approved_amount": 0},
  "vehicle":  {"manufacturing_year": 2014, "purchase_date": "2014-08-01"},
  "history":  {"customer_claims_last_12_months": 0, "vehicle_claims_last_12_months": 0,
               "customer_rejected_claims": 0, "similar_claims": []},
  "documents":{"types": ["KYC", "ADDRESS_PROOF", "VEHICLE_REGISTRATION"], "count": 3, "rejected_count": 0,
               "reused_in_other_claims": 0}
}
```
Response:
```json
{"risk_score": 72, "risk_level": "HIGH", "flagged": true, "engine": "rules-v1",
 "factors": [{"code": "AMOUNT_NEAR_IDV", "category": "Claim amount",
              "description": "Requested amount is 94% of the insured value", "weight": 25}]}
```
`GET /health` (no key) · `GET /api/v1/engine` (key). Errors: 401 bad key, 400 `invalid_payload` with `details`.

## Notifications — `/api/notifications/` (own only)

`GET /` `?unread=true` · `GET unread-count/` · `POST {id}/read/` · `POST read-all/`.
Send `X-Background-Poll: 1` on automatic polling so it doesn't count as user activity for the inactivity timeout.

## Dashboards, reports, administration

| | Who | |
|---|---|---|
| `GET /api/dashboard/` | all | Role-specific: customer summary, adjuster queues, SIU queue, admin KPIs and charts. Every figure is a live query. |
| `GET /api/reports/?report=claims\|fraud\|policies\|vehicles\|customers` | M | Filters: `date_from, date_to, claim_type, claim_status, policy_status, risk_level`. Returns `columns, rows (first 500), total_rows, summary`. |
| `GET /api/reports/export/?format=csv\|xlsx\|pdf&report=…` | M | Same filters and rows as above, as a file download (audited) |
| `GET /api/admin/users/?role=STAFF\|CUSTOMER\|ADJUSTER…&search=` | M | |
| `POST /api/admin/users/` | M | `email, full_name, role (ADJUSTER/SIU/ADMIN), employee_id, department?, phone?` → set-password email |
| `POST /api/admin/users/{id}/activate\|deactivate\|unlock/` | M | |
| `GET /api/admin/customers/?search=` | M | With vehicle, policy and claim counts |
| `GET /api/audit-logs/?action=&actor=&entity_type=&entity_id=&date_from=&date_to=` | M | Read-only |
