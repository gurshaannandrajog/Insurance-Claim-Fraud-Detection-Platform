# Requirement traceability

Every REQ-* identifier in the SRS (153 in total) is listed. Paths are relative to `backend/apps/` (backend, database,
tests) or `frontend/src/` (frontend). Test names refer to `tests/` inside each app; **E2E** means the browser scenario in
`tests/e2e/demo_flow.py`, and **PERF** means `tests/performance/load_check.py`.

Status: ✅ implemented and tested · ◐ implemented, deployment-dependent (explained in the notes).

## 4.1 Authentication & authorisation

| Req | Feature | Backend | Database | Frontend | Test | |
|---|---|---|---|---|---|---|
| AUTH-001 | Customer registration | `accounts/services.register_customer`, `RegisterView` | `User`, `CustomerProfile` | `pages/public/AuthPages › RegisterPage` | `test_auth › test_register_sends_verification…`, E2E | ✅ |
| AUTH-002 | Email verification before login | signed token `make_verification_token` / `verify_email`; login refuses `email_not_verified` | `User.is_email_verified` | `VerifyEmailPage`, resend link on login | same test, `test_invalid_verification_token`, E2E | ✅ |
| AUTH-003 | Email + password login | `authenticate_user`, `LoginView` (session) | `django_session` | `LoginPage`, `AuthContext` | `LoginLockoutTests`, E2E | ✅ |
| AUTH-004 | Password policy | `accounts/validators.ComplexityValidator` + min length 8 | – | live rule checklist | `test_password_policy_enforced` | ✅ |
| AUTH-005 | 4 failures → 20-minute lock | row-locked counter in `authenticate_user` | `failed_login_attempts`, `locked_until` | lock banner (423) | `test_four_failures_lock_account_for_20_minutes` | ✅ |
| AUTH-006 | 30-minute inactivity timeout | `accounts/middleware.InactivityTimeoutMiddleware` | session `_last_activity` | redirect with "signed out after 30 minutes" | `SessionTimeoutTests` (2) | ✅ |
| AUTH-007 | Password reset by email | `request_password_reset`, `reset_password` (single-use token) | – | Forgot / Reset pages | `PasswordResetTests` (3) | ✅ |
| AUTH-008 | RBAC for 4 roles | `accounts/permissions` (`IsCustomer`, `IsAdjuster`, …) | `User.role` | role-based sidebar and routes (`App.tsx RequireRole`) | `test_authorization_matrix` | ✅ |
| AUTH-009 | Nothing outside a role's authority | permission classes on every view + object scoping in `claims/selectors.claims_visible_to` | – | "no access" page | matrix test, E2E security checks | ✅ |
| AUTH-010 | Hashed passwords | PBKDF2-SHA256 (`PASSWORD_HASHERS`) | `User.password` | – | `test_register…` (stored hash ≠ password) | ✅ |

## 4.2 Customer management

| Req | Feature | Backend | Database | Frontend | Test | |
|---|---|---|---|---|---|---|
| CUST-001 | View / update profile | `ProfileView` | `CustomerProfile` | `ProfilePage` | `test_customer_updates_allowed_fields_only` | ✅ |
| CUST-002 | Name, phone, address editable | `ProfileUpdateSerializer` | – | `ProfilePage` | same | ✅ |
| CUST-003 | Email and date of birth immutable | serializer rejects both fields | – | fields disabled | same (400 for both) | ✅ |
| CUST-004 | Customer dashboard | `DashboardView.customer` | – | `CustomerDashboard` | `test_role_dashboards`, E2E | ✅ |
| CUST-005 | View own policies and vehicles | `PolicyViewSet`, `VehicleViewSet` (scoped) | – | Policies, Vehicles pages | `test_customer_sees_only_own_policies` | ✅ |
| CUST-006 | Multiple vehicles and policies | no limit; one live policy per vehicle | FK `Vehicle.customer`, `Policy.customer` | – | seed data (Rohan has 4 vehicles / 2 live policies) | ✅ |
| CUST-007 | Account deletion only without active claims | `delete_customer_account` (deactivate + anonymise, history kept) | `User.deleted_at` | Profile › Delete account | `test_account_deletion_blocked_by_active_claim`, `…without_active_claims` | ✅ |
| CUST-008 | No access to other customers' data | queryset scoping → 404 | – | – | vehicle, policy, claim and document IDOR tests | ✅ |

## 4.3 Insurance policy management

| Req | Feature | Backend | Database | Frontend | Test | |
|---|---|---|---|---|---|---|
| POL-001 | Customers request policies | `create_policy_request` | `PolicyRequest` | Request policy dialog | `test_request_and_admin_approval…`, E2E | ✅ |
| POL-002 | Admin reviews and creates policies | `approve_policy_request` / `reject_policy_request` | – | `PolicyRequestsAdmin` | same, `test_reject_request_requires_reason` | ✅ |
| POL-003 | Unique number; one customer + one vehicle | `assign_number` (PK-based `POL-YYYY-NNNNNN`) | `policy_number UNIQUE`, FKs | – | same | ✅ |
| POL-004 | Start, end, IDV, premium, status stored | `Policy` | columns + CHECK `end_date > start_date`, `idv > 0` | policy cards | same | ✅ |
| POL-005 | New policy is Active | `approve_policy_request` | default `ACTIVE` | – | same | ✅ |
| POL-006 | Customers cannot modify policies | `PolicyViewSet` is read-only (no PUT/PATCH) | – | no edit controls | matrix test | ✅ |
| POL-007 | Multiple policies, different vehicles | `vehicle_has_live_policy` check | – | – | `test_vehicle_cannot_have_two_live_policies` | ✅ |
| POL-008 | Status from cumulative amount vs IDV | `policies/services.recalculate_status` | `cumulative_approved_amount`, CHECK `≤ idv` | progress bar on policy card | `PolicyStatusTests` | ✅ |
| POL-009 | Partially Claimed | same | – | badge | `test_partially_claimed_then_claimed`, E2E | ✅ |
| POL-010 | Claimed | same | – | badge | same | ✅ |
| POL-011 | Expiry | `expire_due_policies` (`run_maintenance` + lazy call on listing) | index `(end_date, status)` | badge | `test_expiry` | ✅ |
| POL-012 | Admin cancellation | `cancel_policy` (blocked while claims are open) | `cancelled_*` | `PoliciesAdmin` | `test_cancellation_by_admin_only…` | ✅ |
| POL-013 | No claims on Claimed / Expired / Cancelled | `is_claimable` | – | wizard lists only claimable policies | `test_claimed_policy_accepts_no_new_claims`, `test_expired_cancelled_and_claimed…` | ✅ |
| POL-014 | New policy after Expired / Cancelled | `vehicle_has_live_policy` | – | "Request policy" shown when uninsured | `test_vehicle_cannot_have_two_live_policies` | ✅ |
| POL-015 | Config changes don't affect existing policies | plan terms copied into each policy | `Policy.plan_name`, `premium_rate_percent`, `premium_amount` | `PlansAdmin` note | `test_plan_change_does_not_affect_existing_policies` | ✅ |
| POL-016 | Customers see only their own policies | scoped queryset | – | – | `test_customer_sees_only_own_policies` | ✅ |

## 4.4 Vehicle management

| Req | Feature | Backend | Database | Frontend | Test | |
|---|---|---|---|---|---|---|
| VEH-001 | Multiple vehicles | `create_vehicle` | FK | `VehiclesPage` | `test_register_vehicle…` | ✅ |
| VEH-002 | All vehicle attributes | `Vehicle` model + serializer validation | columns | vehicle form | same | ✅ |
| VEH-003 | Registered owner stored separately | `owner_name / owner_phone / owner_address` | columns | "Registered owner" fieldset | – (schema) | ✅ |
| VEH-004 | Unique registration number | service check + DB unique index (race-safe) | `UNIQUE(registration_number)` (also engine, chassis) | inline error | `test_duplicate_registration_rejected`, E2E | ✅ |
| VEH-005 | Vehicle ↔ policy | `Policy.vehicle` FK | FK | – | policy tests | ✅ |
| VEH-006 | ≤ 1 active policy | checked under `SELECT … FOR UPDATE` on the vehicle row | index `(vehicle, status)` | – | `test_approval_rechecks_live_policy` | ✅ |
| VEH-007 | New policy after Expired / Cancelled | as POL-014 | – | – | same | ✅ |
| VEH-008 | No new policy while Active / Partially Claimed / Claimed | `PolicyStatus.live()` | – | – | same (all 3 statuses tested) | ✅ |
| VEH-009 | Vehicle locked after policy association | `update_vehicle` → 409 `vehicle_locked` | – | lock notice, edit hidden | `test_vehicle_locked_after_policy_association` | ✅ |
| VEH-010 | No deletion; history retained | no DELETE route; `on_delete=PROTECT` | PROTECT FKs | – | `test_vehicles_cannot_be_deleted` (405) | ✅ |
| VEH-011 | View vehicles and policy info | `current_policy` in serializer | – | vehicle cards | – | ✅ |
| VEH-012 | No access to others' vehicles | scoped queryset | – | – | `test_customers_cannot_see_other_customers_vehicles` | ✅ |

## 4.5 Claim management

| Req | Feature | Backend | Database | Frontend | Test | |
|---|---|---|---|---|---|---|
| CLM-001 | Accident, fire, third-party claims | `submit_claim` | `ClaimType` | `NewClaimPage` wizard | `test_valid_submission_end_to_end`, E2E | ✅ |
| CLM-002 | Claim ↔ customer, vehicle, policy | relationship validated in `submit_claim`; claim stores policy only (single source of truth) | FK `Claim.policy` | – | `test_policy_must_belong_to_customer_and_vehicle` | ✅ |
| CLM-003 | Unique number, status Submitted | `assign_number` `CLM-YYYY-NNNNNN` | `UNIQUE(claim_number)` | – | `test_valid_submission…` | ✅ |
| CLM-004 | No claims on Claimed / Expired / Cancelled | `_check_policy` | – | – | `test_expired_cancelled_and_claimed_policies_rejected` | ✅ |
| CLM-005 | Incident details | `ClaimInputSerializer` + `_validate_incident` (not future, within policy period, amount ≤ remaining IDV) | columns, CHECK `requested_amount > 0` | step 2 of wizard | `test_incident_must_be_in_policy_period…`, `test_amount_cannot_exceed_remaining_idv` | ✅ |
| CLM-006 | 30-minute edit window, closed by review | `edit_claim` checks status, `review_started_at` and `edit_deadline` on the server | `submitted_at`, `review_started_at` | countdown + edit dialog | `ClaimEditWindowTests` (4), E2E | ✅ |
| CLM-007 | Adjuster review → Documents Pending | `start_review`, `request_documents` | `ClaimStatusHistory` | `StaffClaimDetail` | `test_documents_pending_and_resume` | ✅ |
| CLM-008 | Requested and approved amounts separate | separate columns; requested never written after submission | CHECK `approved ≤ requested` | both shown | `test_approval_updates_policy_atomically` | ✅ |
| CLM-009 | Adjuster sets approved amount | `approve_claim(approved_amount, notes)` | `assessment_notes` | approve dialog | same, `test_approved_amount_limits` | ✅ |
| CLM-010 | Update policy cumulative amount | `apply_approved_claim_amount` inside the approval transaction | `cumulative_approved_amount` | policy card | same, `test_approval_rolls_back_completely_on_failure` | ✅ |
| CLM-011 | Fraud score + flag, never auto-reject | `fraud/services.run_assessment` | `FraudAssessment`, `Claim.is_flagged` | risk meter | `test_high_risk_goes_to_fraud_review_not_rejection` | ✅ |
| CLM-012 | Approve / reject, reason required | `approve_claim`, `reject_claim` | CHECK `rejection_reason <> ''` when rejected | dialogs | `test_rejection_requires_reason` | ✅ |
| CLM-013 | Appeal with information and evidence | `submit_appeal` (+ documents tied to the appeal) | `Appeal`, `ClaimDocument.appeal` | `AppealModal` | `AppealTests` | ✅ |
| CLM-014 | Adjuster decides on further appeals | `reject_claim(allow_further_appeal)` required after an appeal; `decide_appeal` | `further_appeal_allowed` | select in reject / appeal dialogs | `test_full_appeal_cycle…`, `test_declined_appeal…` | ✅ |
| CLM-015 | Permanent rejection | `PERMANENTLY_REJECTED` (terminal in `workflow.TRANSITIONS`) | status | badge + "decision is final" | `test_full_appeal_cycle_to_permanent_rejection` | ✅ |
| CLM-016 | Duplicate check | `find_duplicate` (vehicle + incident date + claim type; withdrawn claims ignored) | index `(policy, incident_date, claim_type)` | – | `test_duplicate_claim_for_same_incident` | ✅ |
| CLM-017 | Block duplicates | 409 `duplicate_claim` on submit and on edit | – | error banner | same, `test_withdrawn_claim_does_not_block_resubmission` | ✅ |
| CLM-018 | Claim event notifications | `notify()` on submit, review, documents requested, approve, reject, appeal events | `Notification` | bell, notifications page | `test_claim_submission_notifies_customer`, E2E | ✅ |

## 4.6 Document management

| Req | Feature | Backend | Database | Frontend | Test | |
|---|---|---|---|---|---|---|
| DOC-001 | Customer and adjuster uploads | `documents/services.upload_document` | `ClaimDocument.uploaded_by` | upload dialogs | `test_valid_pdf_and_jpeg`, `test_replacement_keeps_history` | ✅ |
| DOC-002 | PDF / JPG / JPEG only | `validators.validate_upload` (extension + magic bytes) | – | `accept` attribute + pre-check | `test_invalid_extension`, `test_content_must_match_extension`, E2E | ✅ |
| DOC-003 | 10 MB limit | same | CHECK `size_bytes ≤ 10 MB` | pre-check | `test_file_larger_than_10mb_rejected` (incl. exactly 10 MB) | ✅ |
| DOC-004 | Linked to claim | FK | `ClaimDocument.claim` | – | – | ✅ |
| DOC-005 | Supported document types | `DocumentType` (10 types) | – | type selectors | – | ✅ |
| DOC-006 | Mandatory KYC, address, RC; evidence when applicable | mandatory at submission (`missing_documents`); claim-type evidence required **verified** before approval | – | checklist | `test_missing_mandatory_documents`, `test_approval_requires_verified_documents` | ✅ |
| DOC-007 | Pending / Verified / Rejected | `DocumentStatus` | status column | badges | document tests | ✅ |
| DOC-008 | Adjuster verifies / rejects | `verify_document`, `reject_document` | `DocumentReview` history | Verify / Reject buttons | `test_verify_and_reject_with_reason` | ✅ |
| DOC-009 | Rejection reason required | service + DB CHECK | CHECK `document_rejection_has_reason` | required field | same | ✅ |
| DOC-010 | In-app + email on rejection | `notify(..., email=True)` sent after commit | `Notification.email_status` | – | same (Notification row + mail outbox) | ✅ |
| DOC-011 | Adjuster replaces documents during processing | `upload_document(replaces=…)`, old version kept | `replaces` / `is_current` | Replace button, "show replaced versions" | `test_replacement_keeps_history`, E2E | ✅ |
| DOC-012 | No unauthorised access | `can_access_document` on every download; random storage names; no static media URL | – | – | `test_download_access_control` | ✅ |

## 4.7 Fraud detection & risk assessment

| Req | Feature | Backend | Database | Frontend | Test | |
|---|---|---|---|---|---|---|
| FRD-001 | Uses claim, policy, history, vehicle, document and similar-claim data | `fraud/features.build_payload` → Flask `scoring/rules.py` (16 rules) | `request_payload` stored | – | `test_feature_payload`, fraud-service `test_scoring` | ✅ |
| FRD-002 | Score 0–100 | `RuleBasedScorer` (capped) | CHECK `risk_score ≤ 100` | risk meter | `test_score_is_capped_at_100` | ✅ |
| FRD-003 | Low / Medium / High bands | `scoring/base.classify` (Flask) and `fraud/services.classify` (Django re-derives) | – | bands drawn under the meter | `test_risk_bands_match_srs`, `test_classification_bands`, `test_level_is_derived_from_score…` | ✅ |
| FRD-004 | Contributing factors recorded | `FraudIndicator` rows | table | factor list with weights | `test_score_is_sum_of_explained_factor_weights` | ✅ |
| FRD-005 | Flag High risk | `is_flagged` | column | "Flagged" badge | `test_high_risk_goes_to_fraud_review…` | ✅ |
| FRD-006 | Flagged → Fraud Review | `transition(..., FRAUD_REVIEW)` + SIU investigation | `Investigation` | – | same, integration `test_real_engine_flags_a_suspicious_claim` | ✅ |
| FRD-007 | No automatic rejection | no code path rejects from a score; SIU completion returns the claim to the adjuster | – | – | same, `test_complete_investigation_returns_claim_to_adjuster` | ✅ |
| FRD-008 | Adjusters and SIU see score and factors | staff serializer, `/api/fraud/assessments/` | – | Fraud assessment panel, SIU queue | `test_staff_can_view_fraud_details` | ✅ |
| FRD-009 | Admin oversight | same + fraud report | – | analytics, reports | same, `test_claims_report_filters` | ✅ |
| FRD-010 | Hidden from customers | separate customer serializer; `FRAUD_REVIEW` shown as Under Review; internal timeline reasons removed; 403 on the fraud API | `ClaimStatusHistory.is_internal` | – | `test_customer_never_sees_fraud_information` (recursive key scan), E2E | ✅ |
| FRD-011 | SIU records findings | `investigations/services` (start / progress / complete; immutable once completed) | `Investigation`, `InvestigationNote` | investigation panel | `SIUWorkflowTests` (6) | ✅ |
| FRD-012 | Assessments retained | every run stored, including failures | `FraudAssessment` (PROTECT) | assessment run count | `test_assessments_are_retained` | ✅ |

## 4.8 Reporting & analytics

| Req | Feature | Backend | Frontend | Test | |
|---|---|---|---|---|---|
| REP-001 | Customer, vehicle, policy, claim, fraud reports | `reports/queries.REPORTS` | `ReportsPage` tabs | `test_all_report_types` | ✅ |
| REP-002 | Claim status summary | `claims_report.by_status`, dashboard chart | donut chart | `test_admin_dashboard_matches_database` | ✅ |
| REP-003 | Requested, approved and average approved totals | `claims_report.summary` | headline figure + summary | `test_claims_report_filters` | ✅ |
| REP-004 | Claims by type | `by_type` | bar chart | same | ✅ |
| REP-005 | Fraud report | `fraud_report` (flagged, distribution, scores, factors, Fraud Review, investigations) | Fraud tab | same | ✅ |
| REP-006 | Policy statistics | `policies_report` | donut + tab | `test_all_report_types` | ✅ |
| REP-007 | Vehicle statistics | `vehicles_report` (total, insured, make/model) | charts + tab | same | ✅ |
| REP-008 | Customer statistics and registration trend | `customers_report` | line chart + tab | same | ✅ |
| REP-009 | Filters | `filtered_claims`, `filtered_policies`, tz-safe date ranges (`core/filters`) | filter bar | `test_claims_report_filters`, E2E | ✅ |
| REP-010 | Export PDF and CSV/Excel | `reports/exports` (csv / xlsx / pdf from the same rows) | Export buttons | `test_exports_respect_filters`, E2E (Excel) | ✅ |
| REP-011 | Admin only | `IsAdmin` | admin-only routes | `test_reports_are_admin_only` | ✅ |

## 5. Non-functional requirements

| Req | How it is met | Evidence | |
|---|---|---|---|
| PER-001 | Indexed queries, `select_related` / `prefetch_related`, paginated lists | PERF: 25 concurrent users, p95 875 ms, max 1.13 s; single login ≈ 0.4 s | ✅ |
| PER-002 | Claim submission in one transaction; fraud call has a timeout | 4-document claim submitted in 75 ms (local) | ✅ |
| PER-003 | Stateless rules engine; `FRAUD_SERVICE_TIMEOUT_SECONDS=10` | scoring round trip 3–5 ms | ✅ |
| PER-004 | Threaded server, DB row locks only where needed | PERF with 25 concurrent sessions | ✅ |
| PER-005 | Uploads streamed to disk (2 MB in-memory threshold); hashing in chunks | 10 MB upload test | ✅ |
| PER-006 | Targets measured under local conditions | see README › Known limitations | ✅ |
| SAF-001 | Role permissions on every write; no delete endpoints | matrix test | ✅ |
| SAF-002 | `on_delete=PROTECT` on claims, documents, assessments and investigations; replaced documents retained | `test_replacement_keeps_history` | ✅ |
| SAF-003 | Score is an indicator only | FRD-007 tests | ✅ |
| SAF-004 | Role-specific serializers and querysets | FRD-010 and SIU scoping tests | ✅ |
| SEC-001 | `IsAuthenticated` default; 401 for anonymous users | `test_unauthenticated_requests_are_rejected` | ✅ |
| SEC-002 | PBKDF2 hashing | AUTH-010 | ✅ |
| SEC-003 | Email verification | AUTH-002 | ✅ |
| SEC-004 | Email password recovery | AUTH-007 | ✅ |
| SEC-005 | Inactivity timeout | AUTH-006 | ✅ |
| SEC-006 | Lockout | AUTH-005 (+ rate limiting on auth endpoints) | ✅ |
| SEC-007 | RBAC | matrix test | ✅ |
| SEC-008 | Customer data isolation (404) | IDOR tests | ✅ |
| SEC-009 | Adjusters: claim functions only, assigned adjuster only | `test_only_assigned_adjuster_can_act`, matrix | ✅ |
| SEC-010 | SIU sees only claims with an investigation | `test_siu_sees_flagged_claims_only` | ✅ |
| SEC-011 | Admin has no approve / reject authority | `test_admin_and_siu_cannot_decide_claims`, E2E (403) | ✅ |
| SEC-012 | Fraud data hidden from customers | FRD-010 | ✅ |
| SEC-013 | Document access control | DOC-012 | ✅ |
| SEC-014 | Type, content and size validation | DOC-002/003 | ✅ |
| SEC-015 | `ENABLE_HTTPS=true` turns on secure cookies, HSTS and HTTPS redirect | Localhost demo runs on HTTP; HTTPS needs a certificate on the deployment server | ◐ |
| QUA-001 | Consistent role-specific UI | screenshots, E2E | ✅ |
| QUA-002 | Transactions + `on_commit` email | `test_approval_rolls_back_completely_on_failure` | ✅ |
| QUA-003 | Separate Django apps; separate fraud service; service layer | folder structure | ✅ |
| QUA-004 | Stateless API, swappable fraud engine, MySQL | see `docs/ENGINEERING.md` | ✅ |
| QUA-005 | Authentication, authorisation, access control | SEC tests | ✅ |
| QUA-006 | Chrome | E2E runs in Chromium | ✅ |
| QUA-007 | Health endpoints; graceful degradation when the fraud service is down | `test_service_unavailable_degrades_gracefully`, live outage test | ◐ (depends on the host) |

## 5.5 Business rules

| Rule | Implemented by | Test | |
|---|---|---|---|
| BR-001 / 002 / 003 | `vehicle_has_live_policy` under row lock | policy request tests | ✅ |
| BR-004 | `Policy 1─* Claim` | seed data | ✅ |
| BR-005 / 006 | `recalculate_status` | `test_partially_claimed_then_claimed` | ✅ |
| BR-007 | `expire_due_policies` | `test_expiry` | ✅ |
| BR-008 | `cancel_policy` | cancellation test | ✅ |
| BR-009 | `ClaimType` | submission tests | ✅ |
| BR-010 | `edit_claim` | `ClaimEditWindowTests` | ✅ |
| BR-011 | mandatory documents at submission; evidence before approval | document tests | ✅ |
| BR-012 / 013 | `approve_claim` / `reject_claim` (adjusters only) | decision tests | ✅ |
| BR-014 | service + DB CHECK | `test_rejection_requires_reason` | ✅ |
| BR-015 / 016 | appeal workflow | `AppealTests` | ✅ |
| BR-017 / 018 | flag → Fraud Review, never reject | fraud tests | ✅ |
| BR-019 | customer serializer | `test_customer_never_sees_fraud_information` | ✅ |
| BR-020 | Admin excluded from `IsAdjuster` | `test_admin_and_siu_cannot_decide_claims` | ✅ |
| BR-021 | plan snapshot | `test_plan_change_does_not_affect_existing_policies` | ✅ |
| BR-022 | `notify()` in-app + email | notification tests | ✅ |

## Interpretations of the SRS

See `docs/ANALYSIS.md §1` for the 16 ambiguities and the decision taken for each (for example, who makes the final
decision on high-risk claims, and what "Closed" means).
