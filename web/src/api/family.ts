/** Family links (desk side) and the family's own view (public, by token). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { API_BASE, ApiProblem, apiFetch, toProblem } from '@/api/client';
import { keys } from '@/api/queries';
import type { AppealVersion, CheckStarted, FamilyView, ShareCreated, ShareLink } from '@/api/types';

const familyKey = (token: string) => ['family', token] as const;
const sharesKey = (claimId: string) => ['claim', claimId, 'shares'] as const;

// ------------------------------------------------------------------------- desk

export function useShares(claimId: string, enabled: boolean) {
  return useQuery({
    queryKey: sharesKey(claimId),
    queryFn: ({ signal }) => apiFetch<ShareLink[]>(`/claims/${claimId}/shares`, { signal }),
    enabled,
  });
}

export function useCreateShare(claimId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<ShareCreated>(`/claims/${claimId}/shares`, { method: 'POST' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: sharesKey(claimId) });
      void client.invalidateQueries({ queryKey: keys.claim(claimId) });
      void client.invalidateQueries({ queryKey: keys.log(claimId) });
    },
  });
}

export function useRevokeShare(claimId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (sha: string) =>
      apiFetch<ShareLink>(`/claims/${claimId}/shares/${sha}/revoke`, { method: 'POST' }),
    onSuccess: () => void client.invalidateQueries({ queryKey: sharesKey(claimId) }),
  });
}

// ------------------------------------------------------------------------- family (by token)

export function useFamily(token: string) {
  return useQuery({
    queryKey: familyKey(token),
    queryFn: ({ signal }) => apiFetch<FamilyView>(`/family/${token}`, { signal }),
    retry: (failures, error) =>
      !(error instanceof ApiProblem && error.status === 404) && failures < 2,
  });
}

function useFamilyWriter(token: string) {
  const client = useQueryClient();
  return (view: FamilyView) => {
    client.setQueryData(familyKey(token), view);
  };
}

export function usePrepareFamily(token: string) {
  const write = useFamilyWriter(token);
  return useMutation({
    mutationFn: () => apiFetch<FamilyView>(`/family/${token}/prepare`, { method: 'POST' }),
    onSuccess: write,
  });
}

export function usePublicAppeal(token: string, enabled: boolean) {
  return useQuery({
    queryKey: [...familyKey(token), 'appeal'],
    queryFn: ({ signal }) => apiFetch<AppealVersion>(`/family/${token}/appeal`, { signal }),
    enabled,
    retry: false,
  });
}

export function useDraftPublicAppeal(token: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<AppealVersion>(`/family/${token}/appeal`, { method: 'POST' }),
    onSuccess: (appeal) => {
      client.setQueryData([...familyKey(token), 'appeal'], appeal);
      void client.invalidateQueries({ queryKey: familyKey(token), exact: true });
    },
  });
}

export function useSignPublicAppeal(token: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      apiFetch<AppealVersion>(`/family/${token}/appeal/sign`, {
        method: 'POST',
        body: { name, declaration: true },
      }),
    onSuccess: (appeal) => {
      client.setQueryData([...familyKey(token), 'appeal'], appeal);
      void client.invalidateQueries({ queryKey: familyKey(token), exact: true });
    },
  });
}

export function publicAppealPdf(token: string): string {
  return `${API_BASE}/family/${token}/appeal.pdf`;
}

// ------------------------------------------------------------------------- free check

export async function startCheck(form: FormData): Promise<CheckStarted> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/check`, {
      method: 'POST',
      body: form,
      headers: { Accept: 'application/json' },
    });
  } catch {
    throw ApiProblem.offline();
  }
  if (!response.ok) throw await toProblem(response);
  return (await response.json()) as CheckStarted;
}
