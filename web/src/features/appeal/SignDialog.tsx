/**
 * Review & sign: the human-in-the-loop gate. A named reviewer, their role and an explicit
 * declaration; the server stores the SHA-256 of exactly this content. Afterwards the hash is
 * shown with the PDF export and a plain-text copy.
 */
import { Copy, Download, FileSignature, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

import { ApiProblem } from '@/api/client';
import { exportUrl, useSignAppeal } from '@/api/queries';
import type { AppealVersion } from '@/api/types';
import { ProblemAlert } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/overlays';
import { Checkbox, Input, Label } from '@/components/ui/primitives';
import { formatMoney } from '@/lib/format';
import { FORUM } from '@/lib/labels';
import { appealAsText } from '@/features/appeal/appealText';

export function SignDialog({
  claimId,
  appeal,
  open,
  onOpenChange,
}: {
  claimId: string;
  appeal: AppealVersion;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [name, setName] = useState('');
  const [role, setRole] = useState('');
  const [declared, setDeclared] = useState(false);
  const sign = useSignAppeal(claimId);
  const signed = appeal.signature;

  async function copy() {
    try {
      await navigator.clipboard.writeText(appealAsText(appeal));
      toast.success('Appeal text copied', { description: 'Paste it into the portal form.' });
    } catch {
      toast.error('Copy is blocked in this browser');
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        wide
        title={signed ? 'Appeal signed' : 'Review and sign'}
        description={
          signed
            ? 'The content below is sealed. Any edit creates a new version that must be signed again.'
            : `You are signing version ${String(appeal.version)} for ${FORUM[appeal.forum].label}, seeking ${formatMoney(appeal.content.relief_amount, { exact: true })}.`
        }
      >
        {signed ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-success-border bg-success-bg p-4 text-success">
              <p className="flex items-center gap-2 font-medium">
                <ShieldCheck className="size-4" aria-hidden />
                Signed by {signed.reviewer_name}, {signed.reviewer_role}
              </p>
              <p className="mt-2 text-xs">Content SHA-256</p>
              <p className="font-mono text-xs break-all text-ink">{signed.content_sha256}</p>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="secondary" onClick={() => void copy()}>
                <Copy aria-hidden />
                Copy text
              </Button>
              <Button asChild>
                <a href={exportUrl(claimId, appeal.version)} download>
                  <Download aria-hidden />
                  Export signed PDF
                </a>
              </Button>
            </div>
          </div>
        ) : (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              sign.mutate(
                {
                  version: appeal.version,
                  body: {
                    reviewer_name: name.trim(),
                    reviewer_role: role.trim(),
                    declaration: true,
                  },
                },
                {
                  onSuccess: () =>
                    toast.success('Appeal signed', {
                      description: 'Sealed with a SHA-256 content hash.',
                    }),
                },
              );
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="reviewer-name">Reviewer’s full name</Label>
                <Input
                  id="reviewer-name"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                  }}
                  autoComplete="name"
                  required
                  minLength={2}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="reviewer-role">Role</Label>
                <Input
                  id="reviewer-role"
                  value={role}
                  onChange={(e) => {
                    setRole(e.target.value);
                  }}
                  placeholder="TPA desk manager"
                  required
                  minLength={2}
                />
              </div>
            </div>
            <div className="flex items-start gap-3 rounded-lg border border-border bg-canvas p-3">
              <Checkbox
                id="declaration"
                checked={declared}
                onCheckedChange={(v) => {
                  setDeclared(v === true);
                }}
                className="mt-0.5"
              />
              <Label htmlFor="declaration" className="font-normal leading-snug text-ink-muted">
                I have read this appeal, checked its references and amounts against the documents,
                and confirm it is accurate to the best of my knowledge. Arzi prepared the draft; I
                am responsible for what is sent.
              </Label>
            </div>
            {sign.isError ? (
              <ProblemAlert
                error={sign.error instanceof ApiProblem ? sign.error : new Error('Signing failed')}
              />
            ) : null}
            <div className="flex justify-end">
              <Button
                type="submit"
                disabled={!declared || name.trim().length < 2 || role.trim().length < 2}
                loading={sign.isPending}
              >
                {sign.isPending ? null : <FileSignature aria-hidden />}
                Sign appeal
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
