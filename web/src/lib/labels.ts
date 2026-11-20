/** Human wording for every enum the API returns. Desk copy: specific, plain, no hype. */
import type {
  AppealForum,
  AppealStatus,
  ClaimMode,
  ClaimStatus,
  DocType,
  LineCategory,
  Severity,
} from '@/api/types';

export const MODE: Record<ClaimMode, { label: string; short: string; needs: string }> = {
  pre_submission: {
    label: 'Pre-submission audit',
    short: 'Pre-submission',
    needs: 'Policy, itemised bill and discharge summary',
  },
  post_deduction: {
    label: 'Deduction appeal',
    short: 'Deduction',
    needs: 'Everything above, plus the insurer’s settlement letter',
  },
  post_rejection: {
    label: 'Rejection appeal',
    short: 'Rejection',
    needs: 'Everything above, plus the insurer’s rejection letter',
  },
};

export const STATUS: Record<
  ClaimStatus,
  { label: string; tone: 'neutral' | 'info' | 'warning' | 'success' | 'danger' | 'navy' }
> = {
  draft: { label: 'Draft', tone: 'neutral' },
  documents_uploaded: { label: 'Ready to audit', tone: 'info' },
  processing: { label: 'Auditing', tone: 'info' },
  audited: { label: 'Audited', tone: 'success' },
  appeal_drafted: { label: 'Appeal drafted', tone: 'warning' },
  in_review: { label: 'Appeal in review', tone: 'warning' },
  signed: { label: 'Appeal signed', tone: 'navy' },
  exported: { label: 'Appeal exported', tone: 'navy' },
  failed: { label: 'Audit failed', tone: 'danger' },
};

export const APPEAL_STATUS: Record<AppealStatus, string> = {
  draft: 'Draft — not reviewed',
  in_review: 'In review',
  signed: 'Signed',
  exported: 'Exported',
};

export const FORUM: Record<AppealForum, { label: string; short: string; blurb: string }> = {
  insurer_gro: {
    label: 'Insurer grievance officer (GRO)',
    short: 'Insurer GRO',
    blurb: 'First step: a written grievance to the insurer.',
  },
  bima_bharosa: {
    label: 'Bima Bharosa (IRDAI portal)',
    short: 'Bima Bharosa',
    blurb: 'IRDAI’s portal forwards the complaint and tracks it. No amount limit.',
  },
  ombudsman: {
    label: 'Insurance Ombudsman',
    short: 'Ombudsman',
    blurb: 'Free and binding on the insurer, after the insurer has had its chance.',
  },
};

export const DOC_TYPE: Record<DocType, string> = {
  policy_schedule: 'Policy schedule',
  policy_wording: 'Policy wording',
  itemised_bill: 'Itemised bill',
  discharge_summary: 'Discharge summary',
  investigation_report: 'Investigation reports',
  implant_invoice: 'Implant invoice',
  insurer_letter: 'Insurer letter',
  other: 'Other document',
};

export const CATEGORY: Record<LineCategory, string> = {
  room: 'Room',
  icu: 'ICU',
  surgeon: 'Surgeon',
  anaesthetist: 'Anaesthetist',
  ot: 'Operation theatre',
  nursing: 'Nursing',
  consultation: 'Consultation',
  pharmacy: 'Pharmacy',
  consumable: 'Consumables',
  implant: 'Implant',
  diagnostics: 'Diagnostics',
  non_payable: 'Non-payable',
  other: 'Other',
};

export const SEVERITY: Record<Severity, { label: string; rank: number }> = {
  critical: { label: 'Critical', rank: 4 },
  high: { label: 'High', rank: 3 },
  medium: { label: 'Medium', rank: 2 },
  low: { label: 'Low', rank: 1 },
  info: { label: 'Info', rank: 0 },
};

/** Rule titles as the desk reads them; the engine's rule IDs stay in the trace. */
export const RULE: Record<string, string> = {
  NON_PAYABLE: 'Non-payable items',
  SUBSUMED_ITEM: 'Item that is part of room or procedure cost',
  ROOM_RENT_EXCESS: 'Room above the rent cap',
  PROP_ROOM_RENT: 'Proportionate deduction',
  ICU_CAP: 'ICU above the daily cap',
  SUB_LIMIT: 'Sub-limit exceeded',
  COPAY: 'Co-payment',
  WAITING_PERIOD: 'Waiting period not yet served',
  WAITING_REJECTION_INVALID: 'Rejection after the waiting period ended',
  MORATORIUM: 'Rejection after the moratorium',
  PROP_WRONGLY_APPLIED: 'Proportionate deduction on excluded items',
  DOC_MISSING: 'Missing claim document',
};

export function ruleTitle(ruleId: string): string {
  return (
    RULE[ruleId] ??
    ruleId
      .replaceAll('_', ' ')
      .toLowerCase()
      .replace(/^\w/, (c) => c.toUpperCase())
  );
}

export const FIX: Record<string, string> = {
  room_downgrade_or_consent: 'Move to an eligible room, or take written upgrade consent',
  icu_tariff_review: 'Review the ICU tariff against the cap',
  collect_from_patient: 'Collect from the patient at discharge',
  bill_within_package: 'Bill within the procedure package',
  inform_patient: 'Tell the patient their share before discharge',
  check_waiting_period: 'Check the waiting period before filing',
  attach_document: 'Attach the missing document',
  file_appeal: 'File an appeal',
};

export const POLICY_TERM: Record<string, string> = {
  room_rent_cap: 'Room-rent cap',
  proportionate_deduction: 'Proportionate deduction',
  icu_cap: 'ICU cap',
  copay: 'Co-payment',
  sub_limit: 'Sub-limits',
  ped_waiting: 'Pre-existing disease waiting',
  specific_waiting: 'Specific waiting periods',
  associated_expenses: 'Associated medical expenses',
  non_payable_cover: 'Non-payable items cover',
  claim_documents: 'Claim documents',
};

export const STAGE: Record<string, { label: string; detail: string }> = {
  extract: { label: 'Reading documents', detail: 'Gemini transcribes each page' },
  redact: { label: 'Removing identifiers', detail: 'Names, numbers and contacts pseudonymised' },
  reconcile: { label: 'Checking the bill', detail: 'Line sums, categories, letter rows' },
  interpret_policy: { label: 'Reading the policy', detail: 'Clauses mapped to each term' },
  audit: { label: 'Applying IRDAI and policy rules', detail: 'Deterministic ₹ calculations' },
  explain_flags: { label: 'Writing explanations', detail: 'Checked against the citation list' },
};
