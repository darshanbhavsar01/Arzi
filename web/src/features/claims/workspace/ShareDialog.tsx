/**
 * Share with family: Arzi writes the explanation in Gujarati, Hindi and English, narrates it, and
 * creates a 7-day link. The link is shown once (only its fingerprint is kept) and can be withdrawn.
 */
import { Copy, ExternalLink, Link2, MessageCircle, Users } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

import { useCreateShare, useRevokeShare, useShares } from '@/api/family';
import type { ShareCreated } from '@/api/types';
import { ProblemAlert } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTrigger } from '@/components/ui/overlays';
import { Badge, Input } from '@/components/ui/primitives';
import { formatDate, formatDateTime } from '@/lib/format';
import { useNow } from '@/lib/hooks';

export function ShareDialog({ claimId }: { claimId: string }) {
  const [open, setOpen] = useState(false);
  const [created, setCreated] = useState<ShareCreated | null>(null);
  const shares = useShares(claimId, open);
  const create = useCreateShare(claimId);
  const revoke = useRevokeShare(claimId);
  const url = created ? `${window.location.origin}${created.url_path}` : '';
  const now = useNow();

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      toast.success('Link copied');
    } catch {
      toast.error('Copy is blocked in this browser');
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) setCreated(null);
      }}
    >
      <DialogTrigger asChild>
        <Button variant="secondary">
          <Users aria-hidden />
          Share with family
        </Button>
      </DialogTrigger>
      <DialogContent
        wide
        title="Share with the family"
        description="A private page explaining this claim in Gujarati, Hindi and English, with audio. It shows no names or ID numbers and expires after 7 days."
      >
        <div className="space-y-5">
          {created ? (
            <div className="space-y-3 rounded-lg border border-success-border bg-success-bg p-4">
              <p className="text-sm font-medium text-success">
                Link ready. It is shown only now; Arzi keeps a fingerprint, not the link.
              </p>
              <div className="flex gap-2">
                <Input
                  readOnly
                  value={url}
                  aria-label="Family link"
                  className="font-mono text-xs"
                  onFocus={(e) => {
                    e.target.select();
                  }}
                />
                <Button variant="secondary" onClick={() => void copy()}>
                  <Copy aria-hidden />
                  Copy
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="secondary" size="sm">
                  <a
                    href={`https://wa.me/?text=${encodeURIComponent(`Your claim at the hospital, explained in Gujarati, Hindi and English: ${url}`)}`}
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    <MessageCircle aria-hidden />
                    Send on WhatsApp
                  </a>
                </Button>
                <Button asChild variant="ghost" size="sm">
                  <a href={created.url_path} target="_blank" rel="noreferrer">
                    <ExternalLink aria-hidden />
                    Open the family page
                  </a>
                </Button>
                <span className="self-center text-xs text-ink-subtle">
                  Expires {formatDate(created.share.expires_at)}
                </span>
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-border bg-canvas p-4">
              <p className="text-sm text-ink-muted">
                The first link for a claim takes a little longer: Arzi writes and narrates the
                explanation once, then reuses it.
              </p>
              {create.isError ? <ProblemAlert error={create.error} className="mt-3" /> : null}
              <Button
                className="mt-3"
                loading={create.isPending}
                onClick={() => {
                  create.mutate(undefined, {
                    onSuccess: (share) => {
                      setCreated(share);
                      toast.success('Family link created', {
                        description: 'Recorded in the audit log.',
                      });
                    },
                  });
                }}
              >
                {create.isPending ? null : <Link2 aria-hidden />}
                {create.isPending
                  ? 'Writing in Gujarati, Hindi and English…'
                  : 'Create a family link'}
              </Button>
            </div>
          )}

          <section aria-labelledby="links-title">
            <h3 id="links-title" className="text-sm font-semibold">
              Links for this claim
            </h3>
            {shares.data?.length ? (
              <ul className="mt-2 divide-y divide-border rounded-lg border border-border">
                {[...shares.data].reverse().map((s) => {
                  const state = s.revoked_at
                    ? 'Withdrawn'
                    : new Date(s.expires_at).getTime() < now
                      ? 'Expired'
                      : 'Active';
                  return (
                    <li
                      key={s.token_sha256}
                      className="flex items-center gap-3 px-3 py-2.5 text-sm"
                    >
                      <span className="font-mono text-xs text-ink-subtle">
                        {s.token_sha256.slice(0, 10)}…
                      </span>
                      <span className="flex-1 text-ink-muted">
                        Created {formatDateTime(s.created_at)} · expires {formatDate(s.expires_at)}
                      </span>
                      <Badge tone={state === 'Active' ? 'success' : 'neutral'}>{state}</Badge>
                      {state === 'Active' ? (
                        <Button
                          variant="danger"
                          size="sm"
                          loading={revoke.isPending && revoke.variables === s.token_sha256}
                          onClick={() => {
                            revoke.mutate(s.token_sha256, {
                              onSuccess: () => toast.success('Link withdrawn'),
                            });
                          }}
                        >
                          Withdraw
                        </Button>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-ink-subtle">
                {shares.isPending ? 'Loading…' : 'No links yet.'}
              </p>
            )}
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
