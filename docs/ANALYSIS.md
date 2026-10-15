# Phase 1 — SRS & Diagram Analysis

Source documents: SRS v1.0 (Mulani & Nandrajog, SPIT, 06/08/2026), activity diagram, sequence diagram,
DFD (Exp 6), WBS/Gantt (Exp 7). This file records how the SRS was interpreted **before** coding, including
every ambiguity and the decision taken. The traceability table in `TRACEABILITY.md` maps each REQ-* to code.

---

## 1. Ambiguities and conflicts found in the SRS (and decisions)

| # | Ambiguity / conflict | Decision | Why |
|---|---|---|---|
| A1 | §2.2 says the **SIU Investigator** "has the authority to approve or reject high-risk claims" and that the adjuster approves only low-risk claims. But REQ-CLM-012, REQ-BR-013, §4.7.2 ("The Claim Adjuster uses the available information when making the final claim decision"), the glossary, the activity diagram and the sequence diagram all give the final decision to the **Claim Adjuster**. | **Claim Adjuster makes every approve/reject decision.** SIU investigates and records findings + a recommendation. A claim in Fraud Review **cannot be decided** until SIU completes the investigation; completing it returns the claim to the adjuster (activity diagram: *Record Investigation Findings → Update Fraud Assessment → Review Claim*). | Numbered functional requirements and both behavioural diagrams outrank the descriptive user-class paragraph; four sources agree against one. |
| A2 | §2.2: adjuster "escalates **medium-risk** claims to the SIU when necessary", while REQ-FRD-005/006 auto-flag only **High** risk. | High risk (60–100) is auto-flagged → `FRAUD_REVIEW`. Adjusters can **manually escalate** any claim under review (typically medium risk) to Fraud Review with a mandatory reason. | Satisfies both statements without contradicting either. |
| A3 | §2.2 says customers can **withdraw** claims; no REQ covers it. | Customer may withdraw only while status is `SUBMITTED` (before review starts) → `CLOSED` (closure reason `WITHDRAWN`). Withdrawn claims don't count as duplicates. | Same window as editing (REQ-BR-010) — a claim is the customer's until an adjuster picks it up. |
| A4 | When does fraud assessment run? Activity diagram: right after submission. Sequence diagram: during adjuster assessment (`assessClaim → calculateRiskScore`). | Runs **automatically after submission**, again **after every customer edit** and **after an appeal reopens a claim**; adjusters can **re-run** it (e.g. if the Flask service was down). Every run is kept (history, REQ-FRD-012). | Earliest possible flagging + adjuster control. |
| A5 | REQ-FRD-006 moves high-risk claims to *Fraud Review*; REQ-BR-010 allows edits for 30 min "before the adjuster begins review". | Editing is allowed only while status is `SUBMITTED`, within 30 min, and before review starts. A claim auto-moved to Fraud Review is **no longer editable**. | Prevents a flagged customer from tweaking a claim to evade the score. Enforced server-side. |
| A6 | Should customers see the status "Fraud Review"? REQ-FRD-010 hides scores and *reasons*. | Customers see **"Under Review"** for `FRAUD_REVIEW`, and internal timeline entries (flagging, escalation, SIU) are shown without their reasons. | Revealing the fraud flag is itself an internal fraud reason. |
| A7 | Appeal flow: activity diagram has the adjuster *accept/decline* the appeal; sequence diagram has accept → upload docs → reopen → re-review → approve / reject → "appeal not allowed". REQ-BR-016: after the first resubmission the adjuster decides whether another appeal is allowed. | `Appeal` entity with `PENDING → ACCEPTED / DECLINED`. First rejection is always appealable. **Accept** → claim reopened (`UNDER_REVIEW`), fraud re-assessed, then approved or rejected again. Whenever a claim that has already been appealed is rejected again — or an appeal is declined — the adjuster must state `allow_further_appeal`; `false` → `PERMANENTLY_REJECTED`. | Implements both diagrams and REQ-CLM-013/14/15 exactly. |
| A8 | "Closed" appears in REQ-REP-002 but no requirement says when. | `CLOSED` = withdrawn by customer, customer accepts a rejection (activity diagram: *Customer appeals? No → Close Claim*), or a rejected claim passes the appeal window (`APPEAL_WINDOW_DAYS`, default 30) — closed by the `run_maintenance` command. | Matches activity diagram. |
| A9 | Which documents are required and when? Activity diagram uploads documents *before* submit. | **At submission:** KYC, Address proof, Vehicle registration (REQ-DOC-006 mandatory set). **Before approval:** those three plus claim-specific evidence (Accident → accident/damage photos; Fire → fire evidence; Third-party → third-party document) must be **Verified**. Missing evidence moves the claim to `DOCUMENTS_PENDING`. | Mandatory docs gate submission; "when applicable" evidence gates approval. |
| A10 | Can an approved amount exceed what was requested, or the policy's remaining IDV? | `0 < approved ≤ requested` and `approved ≤ IDV − cumulative approved`. | An insurer never pays above the insured value; cumulative ≤ IDV keeps Partially Claimed/Claimed meaningful. |
| A11 | REQ-POL-015 / BR-021: config changes must not affect existing policyholders. | Admin-managed `PolicyPlan` (premium rate, term). A policy **copies** plan name, rate, term and premium at creation (snapshot). Editing a plan only affects future policies. | Classic snapshot pattern. |
| A12 | REQ-VEH-006: one active policy per vehicle. MySQL has no partial unique indexes. | Enforced in the service layer inside a transaction with `SELECT … FOR UPDATE` on the vehicle row (serialises concurrent approvals). | Documented DB limitation; correct under concurrency. |
| A13 | REQ-CUST-007 account deletion while history must be retained (REQ-VEH-010, §6.1). | Deletion = deactivate + mark deleted + anonymise login email; vehicles, policies, claims and audit log are retained. Blocked when any non-terminal claim exists. | Satisfies both. |
| A14 | REQ-POL-012 cancellation while claims are being processed. | Cancellation is blocked while the policy has an open (non-terminal) claim. | Avoids approving against a cancelled policy. |
| A15 | Which adjuster handles a claim? | The adjuster who **starts review** becomes the assigned adjuster; only they can act on it. All adjusters can view all claims. | "View assigned/authorized claims"; prevents two adjusters deciding concurrently. |
| A16 | Employee accounts created by Admin: who knows the password? | Admin creates the account; the system emails a **set-password link**. Admin never sees a password. | Least-privilege. |

---

## 2. Roles and permissions

| Capability | Customer | Claim Adjuster | SIU | Administrator |
|---|:-:|:-:|:-:|:-:|
| Register / verify email / profile | ✔ | – | – | – |
| Vehicles (own) | create, edit until insured, view | view | view | view |
| Policy request | create (own vehicles) | – | – | approve / reject |
| Policies | view own | view | view | view, cancel, plan config |
| Submit / edit / withdraw claim | ✔ (own) | – | – | – |
| Start review, request docs, approve, reject | – | ✔ (assigned) | – | **✘** (REQ-SEC-011) |
| Verify / reject / replace documents | upload only | ✔ | view | view |
| Fraud score & factors | **✘** | ✔ | ✔ | ✔ (oversight) |
| Escalate to Fraud Review | – | ✔ | – | – |
| Record investigation findings | – | – | ✔ | – |
| Appeal | file | decide | – | – |
| Users, customers, reports, audit log | – | – | – | ✔ |

---

## 3. Entities and relationships

```
User 1─1 CustomerProfile                 User 1─1 EmployeeProfile (adjuster/SIU/admin)
CustomerProfile 1─* Vehicle              Vehicle 1─* Policy (≤1 in Active/Partially Claimed/Claimed)
CustomerProfile 1─* PolicyRequest *─1 Vehicle,  PolicyRequest *─1 PolicyPlan,  PolicyRequest 1─0..1 Policy
Policy 1─* Claim                         (claim → policy → vehicle/customer: one source of truth)
Claim 1─* ClaimStatusHistory             Claim 1─* ClaimDocument 1─* DocumentReview
ClaimDocument 0..1─1 ClaimDocument (replaces)
Claim 1─* FraudAssessment 1─* FraudIndicator
Claim 1─* Investigation 1─* InvestigationNote
Claim 1─* Appeal                         User 1─* Notification (optional FK → Claim)
AuditLog (actor → User, nullable; entity_type + entity_id)
```

Normalisation note: a claim stores **only** `policy_id`; customer and vehicle are reached through the
(immutable) policy, so they can never disagree. The only deliberate denormalisation is
`Claim.current_risk_score / current_risk_level` (copy of the latest assessment) so that reports and
queues can filter and index by risk without a correlated sub-query.

---

## 4. Claim state machine

```
                 ┌──────── withdraw (customer) ─────────────────────────────┐
                 │                                                          ▼
 SUBMITTED ──start review──► UNDER_REVIEW ──approve──► APPROVED           CLOSED
     │                        │  ▲   │  ▲                                    ▲
     │ high risk (system)     │  │   │  └─resume── DOCUMENTS_PENDING        │ accept decision /
     ▼                        │  │   └─request docs─┘     │                 │ appeal window over
 FRAUD_REVIEW ◄──escalate─────┘  │                        │ reject          │
     │                           │ appeal accepted        ▼                 │
     └─SIU completes ────────────┘──────────────────── REJECTED ────────────┘
       investigation                                      │ reject again / decline appeal,
                                                          │ adjuster: no further appeal
                                                          ▼
                                                PERMANENTLY_REJECTED
```

Every transition is validated against a single transition table (`claims/workflow.py`), records actor,
timestamp and reason in `ClaimStatusHistory`, writes an `AuditLog` row and (where applicable) notifies.

## 5. Policy state machine

```
 (request approved) ─► ACTIVE ─approved claims>0─► PARTIALLY_CLAIMED ─cumulative≥IDV─► CLAIMED
                         │                              │                              │
                         ├──────── end date passed ─────┴──────────────────────────────┴─► EXPIRED
                         └──────── admin cancels (no open claims) ─────────────────────────► CANCELLED
```
New claims are accepted only in ACTIVE / PARTIALLY_CLAIMED (REQ-POL-013). A vehicle may get a new policy
only when its previous one is EXPIRED / CANCELLED (REQ-VEH-007/008).

---

## 6. API plan (see `API.md` for the full reference)

`/api/auth/` · `/api/profile/` · `/api/vehicles/` · `/api/policy-plans/` · `/api/policy-requests/` ·
`/api/policies/` · `/api/claims/` (+ actions) · `/api/documents/` · `/api/fraud/` · `/api/investigations/` ·
`/api/appeals/` · `/api/notifications/` · `/api/dashboard/` · `/api/reports/` · `/api/admin/users/` ·
`/api/admin/customers/` · `/api/audit-logs/`

## 7. Frontend page map

| Role | Pages |
|---|---|
| Public | Login, Register, Verify email, Forgot password, Reset password |
| Customer | Dashboard, Vehicles, Policies & requests, Claims, New claim wizard, Claim detail (edit / upload / appeal / withdraw), Notifications, Profile |
| Claim Adjuster | Operations dashboard, Claims queue (search/filter), Claim workspace (all sections + actions) |
| SIU | Investigation dashboard, Investigation queue, Claim workspace with investigation panel |
| Administrator | Analytics dashboard, Policy requests, Policies, Policy plans, Users, Customers, Claims (read-only oversight), Reports & export, Audit log |

## 8. Architecture

```
React (Vite, TS, Tailwind)  ──HTTP/JSON, session cookie + CSRF──►  Django REST API
                                                                   ├─ views (thin) → services (business rules, transactions)
                                                                   ├─ MySQL (InnoDB, FK + CHECK + UNIQUE constraints)
                                                                   ├─ email (SMTP / console backend)
                                                                   └─ fraud client ──HTTP/JSON + API key──► Flask fraud service
                                                                                                             └─ pluggable scorer (rules today, ML later)
```
