/**
 * Server state, one hook per resource (TanStack Query). Mutations update or invalidate exactly
 * the queries they affect, so screens stay consistent without a global store.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiFetch, idempotencyKey } from '@/api/client';
import type {
  AppealEdit,
  AppealForum,
  AppealVersion,
  AuditLogEntry,
  AuditRun,
  ClaimList,
  ClaimMode,
  ClaimRecord,
  ClaimStatus,
  DemoClaim,
  DocumentOut,
  ForumOption,
  GroComplaint,
  LineCorrection,
  RuleCitation,
  SignRequest,
  Workspace,
} from '@/api/types';

export const keys = {
  claims: (filters: ClaimFilters) => ['claims', filters] as const,
  allClaims: ['claims'] as const,
  claim: (id: string) => ['claim', id] as const,
  documents: (id: string) => ['claim', id, 'documents'] as const,
  runs: (id: string) => ['claim', id, 'runs'] as const,
  log: (id: string) => ['claim', id, 'log'] as const,
  appeals: (id: string) => ['claim', id, 'appeals'] as const,
  forums: (id: string, complaint: GroComplaint | null) =>
    ['claim', id, 'forums', complaint] as const,
  citations: ['citations'] as const,
  workspace: ['workspace'] as const,
};

export interface ClaimFilters {
  status?: ClaimStatus | undefined;
  mode?: ClaimMode | undefined;
  q?: string | undefined;
}

function query(params: Record<string, string | undefined>): string {
  const entries = Object.entries(params).filter((e): e is [string, string] => Boolean(e[1]));
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : '';
}

// ------------------------------------------------------------------------- reads

export function useClaims(filters: ClaimFilters) {
  return useQuery({
    queryKey: keys.claims(filters),
    queryFn: ({ signal }) =>
      apiFetch<ClaimList>(`/claims${query({ ...filters, limit: '100' })}`, { signal }),
    placeholderData: keepPreviousData,
    // Audits started from the worklist finish in seconds: keep rows fresh while any is running.
    refetchInterval: (q) =>
      q.state.data?.items.some((c) => c.status === 'processing') ? 2000 : false,
  });
}

export function useClaim(claimId: string) {
  return useQuery({
    queryKey: keys.claim(claimId),
    queryFn: ({ signal }) => apiFetch<ClaimRecord>(`/claims/${claimId}`, { signal }),
  });
}

export function useDocuments(claimId: string) {
  return useQuery({
    queryKey: keys.documents(claimId),
    queryFn: ({ signal }) => apiFetch<DocumentOut[]>(`/claims/${claimId}/documents`, { signal }),
  });
}

export function useRuns(claimId: string) {
  return useQuery({
    queryKey: keys.runs(claimId),
    queryFn: ({ signal }) => apiFetch<AuditRun[]>(`/claims/${claimId}/runs`, { signal }),
  });
}

export function useAuditLog(claimId: string) {
  return useQuery({
    queryKey: keys.log(claimId),
    queryFn: ({ signal }) => apiFetch<AuditLogEntry[]>(`/claims/${claimId}/audit-log`, { signal }),
  });
}

export function useAppeals(claimId: string, enabled = true) {
  return useQuery({
    queryKey: keys.appeals(claimId),
    queryFn: ({ signal }) => apiFetch<AppealVersion[]>(`/claims/${claimId}/appeals`, { signal }),
    enabled,
  });
}

export function useForums(claimId: string, complaint: GroComplaint | null, enabled = true) {
  return useQuery({
    queryKey: keys.forums(claimId, complaint),
    queryFn: ({ signal }) =>
      apiFetch<ForumOption[]>(
        `/claims/${claimId}/appeals/forums${query({
          gro_filed_on: complaint?.filed_on,
          gro_outcome: complaint?.outcome,
          gro_replied_on: complaint?.replied_on ?? undefined,
        })}`,
        { signal },
      ),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useCitations() {
  return useQuery({
    queryKey: keys.citations,
    queryFn: ({ signal }) => apiFetch<RuleCitation[]>('/meta/citations', { signal }),
    staleTime: Infinity,
    select: (list) => new Map(list.map((c) => [c.id, c])),
  });
}

export function useWorkspace() {
  return useQuery({
    queryKey: keys.workspace,
    queryFn: ({ signal }) => apiFetch<Workspace>('/meta/workspace', { signal }),
    staleTime: 60_000,
  });
}

// ------------------------------------------------------------------------- claim writes

function useClaimWriter() {
  const client = useQueryClient();
  return (claim: ClaimRecord) => {
    client.setQueryData(keys.claim(claim.claim_id), claim);
    void client.invalidateQueries({ queryKey: keys.allClaims });
    void client.invalidateQueries({ queryKey: keys.log(claim.claim_id) });
  };
}

export function useCreateClaim() {
  return useMutation({
    mutationFn: (body: { mode: ClaimMode; insurer_hint?: string }) =>
      apiFetch<ClaimRecord>('/claims', { method: 'POST', body }),
  });
}

export function useRecordConsent() {
  const write = useClaimWriter();
  return useMutation({
    mutationFn: ({ claimId, givenBy }: { claimId: string; givenBy: string }) =>
      apiFetch<ClaimRecord>(`/claims/${claimId}/consent`, {
        method: 'POST',
        body: { given_by: givenBy },
      }),
    onSuccess: write,
  });
}

export function useStartRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (claimId: string) =>
      apiFetch<{ run_id: string; status: string; events_url: string }>(`/claims/${claimId}/runs`, {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey() },
      }),
    onSuccess: (_run, claimId) => {
      void client.invalidateQueries({ queryKey: keys.claim(claimId) });
      void client.invalidateQueries({ queryKey: keys.allClaims });
    },
  });
}

export function useCorrectLine(claimId: string) {
  const write = useClaimWriter();
  return useMutation({
    mutationFn: ({ lineId, body }: { lineId: number; body: LineCorrection }) =>
      apiFetch<ClaimRecord>(`/claims/${claimId}/lines/${String(lineId)}`, {
        method: 'PATCH',
        body,
      }),
    onSuccess: write,
  });
}

export function useReviewFlag(claimId: string) {
  const write = useClaimWriter();
  return useMutation({
    mutationFn: ({
      flagId,
      decision,
      reason = '',
    }: {
      flagId: string;
      decision: 'accepted' | 'dismissed';
      reason?: string;
    }) =>
      apiFetch<ClaimRecord>(`/claims/${claimId}/flags/${flagId}/review`, {
        method: 'POST',
        body: { decision, reason },
      }),
    onSuccess: write,
  });
}

export function useLoadDemo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<DemoClaim[]>('/demo/cases', { method: 'POST' }),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.allClaims }),
  });
}

// ------------------------------------------------------------------------- appeals

function useAppealWriter(claimId: string) {
  const client = useQueryClient();
  return (appeal: AppealVersion) => {
    client.setQueryData<AppealVersion[]>(keys.appeals(claimId), (old) => {
      const others = (old ?? []).filter((a) => a.version !== appeal.version);
      return [...others, appeal].sort((a, b) => a.version - b.version);
    });
    void client.invalidateQueries({ queryKey: keys.claim(claimId) });
    void client.invalidateQueries({ queryKey: keys.allClaims });
    void client.invalidateQueries({ queryKey: keys.log(claimId) });
  };
}

export function useDraftAppeal(claimId: string) {
  const write = useAppealWriter(claimId);
  return useMutation({
    mutationFn: (body: { forum: AppealForum; gro_complaint?: GroComplaint | null }) =>
      apiFetch<AppealVersion>(`/claims/${claimId}/appeals`, {
        method: 'POST',
        body,
        headers: { 'Idempotency-Key': idempotencyKey() },
      }),
    onSuccess: write,
  });
}

export function useEditAppeal(claimId: string) {
  const write = useAppealWriter(claimId);
  return useMutation({
    mutationFn: ({ version, body }: { version: number; body: AppealEdit }) =>
      apiFetch<AppealVersion>(`/claims/${claimId}/appeals/${String(version)}`, {
        method: 'PUT',
        body,
      }),
    onSuccess: write,
  });
}

export function useSubmitAppeal(claimId: string) {
  const write = useAppealWriter(claimId);
  return useMutation({
    mutationFn: (version: number) =>
      apiFetch<AppealVersion>(`/claims/${claimId}/appeals/${String(version)}/submit`, {
        method: 'POST',
      }),
    onSuccess: write,
  });
}

export function useSignAppeal(claimId: string) {
  const write = useAppealWriter(claimId);
  return useMutation({
    mutationFn: ({ version, body }: { version: number; body: SignRequest }) =>
      apiFetch<AppealVersion>(`/claims/${claimId}/appeals/${String(version)}/sign`, {
        method: 'POST',
        body,
      }),
    onSuccess: write,
  });
}

export function exportUrl(claimId: string, version: number, download = true): string {
  return `/api/v1/claims/${claimId}/appeals/${String(version)}/export.pdf${download ? '' : '?download=false'}`;
}

export function documentUrl(claimId: string, documentId: string): string {
  return `/api/v1/claims/${claimId}/documents/${documentId}/content`;
}
