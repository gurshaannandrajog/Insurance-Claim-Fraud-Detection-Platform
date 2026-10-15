export type Role = "CUSTOMER" | "ADJUSTER" | "SIU" | "ADMIN";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  role_display: string;
  is_active: boolean;
  is_email_verified: boolean;
  date_joined: string;
  last_login: string | null;
  customer_profile: {
    phone: string; date_of_birth: string; address_line: string; city: string; state: string; postal_code: string;
  } | null;
  employee_profile: { employee_id: string; department: string; phone: string } | null;
  is_locked?: boolean;
  locked_until?: string | null;
  vehicle_count?: number;
  policy_count?: number;
  claim_count?: number;
}

export interface Vehicle {
  id: number;
  registration_number: string;
  make: string;
  model: string;
  vehicle_type: string;
  vehicle_type_display: string;
  manufacturing_year: number;
  registration_date: string;
  purchase_date: string;
  engine_number: string;
  chassis_number: string;
  color: string;
  owner_name: string;
  owner_phone: string;
  owner_address: string;
  is_locked: boolean;
  current_policy: { id: number; policy_number: string; status: string; end_date: string } | null;
  customer_name: string;
  customer_email: string;
  created_at: string;
}

export interface Plan {
  id: number; code: string; name: string; description: string; premium_rate_percent: string;
  term_months: number; min_idv: string; max_idv: string; is_active: boolean;
}

export interface VehicleBrief {
  id: number; registration_number: string; make: string; model: string; vehicle_type: string;
  manufacturing_year: number; color: string;
}

export interface PolicyRequest {
  id: number; vehicle: VehicleBrief; plan: Plan; requested_idv: string; notes: string; status: string;
  status_display: string; customer_name: string; customer_email: string; reviewed_by_name: string | null;
  reviewed_at: string | null; decision_note: string; policy_number: string | null; created_at: string;
}

export interface Policy {
  id: number; policy_number: string; vehicle: VehicleBrief; plan_name: string; premium_rate_percent: string;
  start_date: string; end_date: string; idv: string; premium_amount: string; cumulative_approved_amount: string;
  remaining_idv: string; status: string; status_display: string; customer_name: string; customer_email: string;
  claim_count: number; is_claimable: boolean; cancelled_at: string | null; cancellation_reason: string;
}

export interface ClaimListItem {
  id: number; claim_number: string; claim_type: string; claim_type_display: string; incident_date: string;
  requested_amount: string; approved_amount: string | null; status: string; status_display: string;
  vehicle_registration: string; policy_number: string; submitted_at: string; updated_at: string;
  customer_name?: string; assigned_adjuster_name?: string | null; current_risk_score?: number | null;
  current_risk_level?: string; is_flagged?: boolean;
}

export interface ClaimDocument {
  id: number; document_type: string; document_type_display: string; original_filename: string;
  content_type: string; size_bytes: number; status: string; status_display: string; is_current: boolean;
  replaces: number | null; replaced_by_id: number | null; appeal: number | null; uploaded_by_name: string;
  uploaded_by_role: string; uploaded_at: string; verified_by_name: string | null; verified_at: string | null;
  rejection_reason: string; download_url: string;
  reviews: { id: number; action: string; actor_name: string; reason: string; created_at: string }[];
}

export interface ChecklistItem { label: string; types: string[]; provided: boolean; verified: boolean; rejected: boolean }

export interface TimelineEntry {
  id: number; from_status: string; to_status: string; to_status_display: string; reason: string;
  actor: string | null; created_at: string; is_internal?: boolean;
}

export interface Appeal {
  id: number; claim_id: number; claim_number: string; sequence: number; reason: string; status: string;
  status_display: string; decided_by_name: string | null; decided_at: string | null; decision_note: string;
  further_appeal_allowed: boolean | null; created_at: string;
}

export interface FraudAssessment {
  id: number; status: string; trigger: string; risk_score: number | null; risk_level: string;
  risk_level_display: string; flagged: boolean; engine: string; error_message: string; response_ms: number | null;
  requested_by_name: string | null; created_at: string;
  indicators: { code: string; category: string; description: string; weight: number }[];
}

export interface Investigation {
  id: number; claim_id: number; claim_number: string; claim_type: string; claim_status: string;
  requested_amount: string; customer_name: string; risk_score: number | null; risk_level: string;
  top_factors: string[]; trigger: string; trigger_display: string; trigger_reason: string;
  opened_by_name: string | null; investigator_name: string | null; status: string; status_display: string;
  findings: string; evidence_notes: string; recommendation: string; recommendation_display: string;
  created_at: string; started_at: string | null; completed_at: string | null;
  notes: { id: number; author_name: string; note: string; created_at: string }[];
}

interface ClaimCommon extends ClaimListItem {
  incident_time: string; incident_location: string; description: string; rejection_reason: string;
  decided_at: string | null; further_appeal_allowed: boolean; appeal_count: number; closure_reason: string;
  vehicle: VehicleBrief & { owner_name: string; engine_number: string; chassis_number: string };
  policy: {
    id: number; policy_number: string; plan_name: string; status: string; status_display: string;
    start_date: string; end_date: string; idv: string; cumulative_approved_amount: string; remaining_idv: string;
  };
  timeline: TimelineEntry[]; documents: ClaimDocument[]; document_checklist: ChecklistItem[]; appeals: Appeal[];
  actions: string[]; edit_deadline: string;
}

export interface CustomerClaim extends ClaimCommon {
  is_editable: boolean; edit_seconds_remaining: number; appeal_deadline: string | null;
}

export interface StaffClaim extends ClaimCommon {
  assessment_notes: string; decided_by_name: string | null; review_started_at: string | null;
  siu_cleared_at: string | null;
  customer: { id: number; full_name: string; email: string; phone: string; address: string; member_since: string };
  fraud_assessments: FraudAssessment[]; investigations: Investigation[];
  customer_claim_history: {
    id: number; claim_number: string; claim_type: string; incident_date: string; status: string;
    status_display: string; requested_amount: string; approved_amount: string | null; vehicle_registration: string;
  }[];
}

export interface Notification {
  id: number; type: string; type_display: string; title: string; message: string; claim: number | null;
  link: string; is_read: boolean; created_at: string;
}

export interface Bucket { key?: string; label: string; value: number }
