export type Tone = "neutral" | "info" | "ok" | "warn" | "bad" | "cover";

export const CLAIM_STATUS_TONE: Record<string, Tone> = {
  SUBMITTED: "info", UNDER_REVIEW: "cover", DOCUMENTS_PENDING: "warn", FRAUD_REVIEW: "bad",
  APPROVED: "ok", REJECTED: "bad", CLOSED: "neutral", PERMANENTLY_REJECTED: "bad",
};
export const POLICY_STATUS_TONE: Record<string, Tone> = {
  ACTIVE: "ok", PARTIALLY_CLAIMED: "cover", CLAIMED: "warn", EXPIRED: "neutral", CANCELLED: "bad",
};
export const DOC_STATUS_TONE: Record<string, Tone> = { PENDING: "warn", VERIFIED: "ok", REJECTED: "bad" };
export const RISK_TONE: Record<string, Tone> = { LOW: "ok", MEDIUM: "warn", HIGH: "bad" };
export const REQUEST_TONE: Record<string, Tone> = { PENDING: "warn", APPROVED: "ok", REJECTED: "bad", WITHDRAWN: "neutral" };
export const INVESTIGATION_TONE: Record<string, Tone> = { OPEN: "warn", IN_PROGRESS: "info", COMPLETED: "ok" };

export const CLAIM_TYPES = [
  { value: "ACCIDENT", label: "Accident" },
  { value: "FIRE", label: "Fire" },
  { value: "THIRD_PARTY", label: "Third-party damage" },
];

export const CLAIM_STATUSES = [
  ["SUBMITTED", "Submitted"], ["UNDER_REVIEW", "Under Review"], ["DOCUMENTS_PENDING", "Documents Pending"],
  ["FRAUD_REVIEW", "Fraud Review"], ["APPROVED", "Approved"], ["REJECTED", "Rejected"], ["CLOSED", "Closed"],
  ["PERMANENTLY_REJECTED", "Permanently Rejected"],
] as const;

export const POLICY_STATUSES = [
  ["ACTIVE", "Active"], ["PARTIALLY_CLAIMED", "Partially Claimed"], ["CLAIMED", "Claimed"],
  ["EXPIRED", "Expired"], ["CANCELLED", "Cancelled"],
] as const;

export const DOCUMENT_TYPES: { value: string; label: string; staffOnly?: boolean }[] = [
  { value: "KYC", label: "KYC details" },
  { value: "ADDRESS_PROOF", label: "Address proof" },
  { value: "VEHICLE_REGISTRATION", label: "Vehicle registration (RC)" },
  { value: "POLICY_HISTORY", label: "Policy history" },
  { value: "ACCIDENT_PHOTO", label: "Accident photograph" },
  { value: "FIRE_EVIDENCE", label: "Fire photograph / evidence" },
  { value: "DAMAGE_PHOTO", label: "Vehicle damage photograph" },
  { value: "THIRD_PARTY_DOCUMENT", label: "Third-party document" },
  { value: "REPAIR_ESTIMATE", label: "Repair estimate", staffOnly: true },
  { value: "OTHER", label: "Other supporting document" },
];

export const EVIDENCE_FOR: Record<string, string> = {
  ACCIDENT: "ACCIDENT_PHOTO", FIRE: "FIRE_EVIDENCE", THIRD_PARTY: "THIRD_PARTY_DOCUMENT",
};

export const VEHICLE_TYPES = [
  ["CAR", "Car"], ["SUV", "SUV"], ["MOTORCYCLE", "Motorcycle"], ["SCOOTER", "Scooter"],
  ["COMMERCIAL", "Commercial vehicle"], ["OTHER", "Other"],
] as const;

export const RECOMMENDATIONS = [
  ["LEGITIMATE", "No fraud indicators confirmed"],
  ["SUSPICIOUS", "Suspicious — proceed with caution"],
  ["FRAUDULENT", "Fraud confirmed — recommend rejection"],
  ["INCONCLUSIVE", "Inconclusive"],
] as const;

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const ACCEPT_FILES = ".pdf,.jpg,.jpeg,application/pdf,image/jpeg";

/** Client-side pre-check for a better UX; the server re-validates everything. */
export function checkFile(f: File): string | null {
  const ext = f.name.split(".").pop()?.toLowerCase();
  if (!ext || !["pdf", "jpg", "jpeg"].includes(ext)) return "Only PDF, JPG and JPEG files are accepted.";
  if (f.size > MAX_UPLOAD_BYTES) return `File is ${(f.size / 1048576).toFixed(1)} MB — the limit is 10 MB.`;
  if (f.size === 0) return "The file is empty.";
  return null;
}
