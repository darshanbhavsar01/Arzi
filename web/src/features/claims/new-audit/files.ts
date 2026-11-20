/** Client-side checks and hints for the documents a claim needs. The pipeline has the final say. */
import type { ClaimMode, DocType } from '@/api/types';

export const MAX_FILE_BYTES = 20 * 1024 * 1024;
export const ACCEPTED = ['application/pdf', 'image/jpeg', 'image/png'];

export interface PickedFile {
  id: string;
  file: File;
  type: DocType | null;
  progress: number;
  state: 'ready' | 'uploading' | 'uploaded' | 'error';
  error?: string;
}

/** A guess from the file name, used only to tick the checklist; the model classifies for real. */
export function guessType(name: string): DocType | null {
  const n = name.toLowerCase();
  if (/letter|settlement|rejection|repudiat|deduction/.test(n)) return 'insurer_letter';
  if (n.includes('schedule')) return 'policy_schedule';
  if (/wording|policy/.test(n)) return 'policy_wording';
  if (/bill|invoice_final|scan/.test(n) && !n.includes('implant')) return 'itemised_bill';
  if (n.includes('discharge')) return 'discharge_summary';
  if (/report|lab|radiolog|investigation/.test(n)) return 'investigation_report';
  if (/implant|sticker/.test(n)) return 'implant_invoice';
  return null;
}

export interface Requirement {
  id: string;
  label: string;
  required: boolean;
  types: DocType[];
}

export function requirements(mode: ClaimMode): Requirement[] {
  const base: Requirement[] = [
    {
      id: 'policy',
      label: 'Policy schedule or wording',
      required: true,
      types: ['policy_schedule', 'policy_wording'],
    },
    { id: 'bill', label: 'Itemised hospital bill', required: true, types: ['itemised_bill'] },
    { id: 'discharge', label: 'Discharge summary', required: true, types: ['discharge_summary'] },
    {
      id: 'reports',
      label: 'Investigation reports',
      required: false,
      types: ['investigation_report'],
    },
    {
      id: 'implant',
      label: 'Implant invoice (if an implant was used)',
      required: false,
      types: ['implant_invoice'],
    },
  ];
  if (mode === 'pre_submission') return base;
  const letter =
    mode === 'post_deduction' ? 'Insurer’s settlement letter' : 'Insurer’s rejection letter';
  return [
    ...base.slice(0, 3),
    { id: 'letter', label: letter, required: true, types: ['insurer_letter'] },
    ...base.slice(3),
  ];
}

/** Which requirements the picked files appear to cover (chosen type, else the name's hint). */
export function coverage(mode: ClaimMode, files: PickedFile[]): Map<string, boolean> {
  const types = new Set(files.map((f) => f.type ?? guessType(f.file.name)).filter(Boolean));
  return new Map(requirements(mode).map((r) => [r.id, r.types.some((t) => types.has(t))]));
}

export function rejectReason(file: File): string | null {
  if (!ACCEPTED.includes(file.type)) return 'Upload a PDF, JPEG or PNG.';
  if (file.size > MAX_FILE_BYTES) return 'Files can be at most 20 MB.';
  return null;
}

export function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${String(Math.max(1, Math.round(bytes / 1024)))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
