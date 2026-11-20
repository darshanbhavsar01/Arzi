/** Settings: hospital profile and tariff, team, data and privacy, and how the AI is running. */
import { BedDouble, Cpu, Lock, Users } from 'lucide-react';
import type { ReactNode } from 'react';

import { useWorkspace } from '@/api/queries';
import { Money } from '@/components/domain';
import { PageHeader, ProblemAlert } from '@/components/states';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/overlays';
import { Badge, Card, Progress, Skeleton } from '@/components/ui/primitives';

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[14rem_1fr] gap-4 px-5 py-3">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

export default function SettingsPage() {
  const workspace = useWorkspace();
  if (workspace.isPending)
    return (
      <div className="space-y-4" role="status" aria-label="Loading settings">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-96" />
      </div>
    );
  if (workspace.isError)
    return <ProblemAlert error={workspace.error} onRetry={() => void workspace.refetch()} />;
  const w = workspace.data;
  const used = w.daily_budget_inr ? w.spent_today_inr / w.daily_budget_inr : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Hospital profile, team, data handling and the AI configuration this workspace runs on."
      />
      <Card className="overflow-hidden">
        <Tabs defaultValue="hospital">
          <TabsList aria-label="Settings sections">
            <TabsTrigger value="hospital">
              <BedDouble className="size-4" aria-hidden />
              Hospital
            </TabsTrigger>
            <TabsTrigger value="team">
              <Users className="size-4" aria-hidden />
              Team
            </TabsTrigger>
            <TabsTrigger value="privacy">
              <Lock className="size-4" aria-hidden />
              Data and privacy
            </TabsTrigger>
            <TabsTrigger value="system">
              <Cpu className="size-4" aria-hidden />
              System
            </TabsTrigger>
          </TabsList>

          <TabsContent value="hospital">
            <dl className="divide-y divide-border">
              <Row label="Hospital">{w.hospital?.name ?? '—'}</Row>
              <Row label="City">{w.hospital?.city ?? '—'}</Row>
              <Row label="Workspace ID">
                <span className="font-mono text-[0.8125rem]">{w.hospital_id}</span>
              </Row>
            </dl>
            <div className="border-t border-border px-5 py-4">
              <h2 className="text-sm font-semibold">Room categories and rates</h2>
              <p className="mt-0.5 text-xs text-ink-subtle">
                Used when a policy caps room rent by category (for example “single private AC”).
              </p>
              <table className="mt-3 w-full max-w-xl text-sm">
                <caption className="sr-only">Room tariff</caption>
                <thead className="text-xs text-ink-muted">
                  <tr>
                    <th scope="col" className="py-1.5 text-left font-medium">
                      Category
                    </th>
                    <th scope="col" className="py-1.5 text-right font-medium">
                      Rate a day
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {(w.hospital?.room_categories ?? []).map((r) => (
                    <tr key={r.name}>
                      <td className="py-2">{r.name}</td>
                      <td className="py-2 text-right">
                        <Money paise={r.rate_per_day} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </TabsContent>

          <TabsContent value="team">
            <dl className="divide-y divide-border">
              <Row label="Signed in as">
                {w.user_name} <Badge className="ml-2">{w.user_role.replace('_', ' ')}</Badge>
              </Row>
              <Row label="Sign-in">
                Demo workspace for one hospital. Every action is recorded with the user in the
                claim’s audit log.
              </Row>
              <Row label="Who can sign appeals">
                Any named reviewer; their name, role, time and the content hash are recorded on
                every signature.
              </Row>
            </dl>
          </TabsContent>

          <TabsContent value="privacy">
            <dl className="divide-y divide-border">
              <Row label="Data location">
                Google Cloud {w.region} (Mumbai): documents, claim records and audit logs.
              </Row>
              <Row label="Identifiers">
                Names, phone numbers, Aadhaar-like and PAN-like numbers, emails, policy, member and
                UHID numbers are replaced with pseudonyms before any AI reasoning. Originals are
                kept apart and used only to print a signed letter.
              </Row>
              <Row label="Consent">
                Recorded on every claim before its documents are processed (purpose: claim audit),
                in the claim’s append-only audit log.
              </Row>
              <Row label="Retention">Uploaded documents are deleted after 30 days.</Row>
              <Row label="Data in this workspace">
                <Badge tone="warning">Synthetic</Badge>{' '}
                <span className="ml-1 text-ink-muted">
                  All demo patients, hospitals and insurers are fictional.
                </span>
              </Row>
            </dl>
          </TabsContent>

          <TabsContent value="system">
            <dl className="divide-y divide-border">
              <Row label="AI mode">
                <Badge tone={w.llm_mode === 'live' ? 'success' : 'info'}>{w.llm_mode}</Badge>{' '}
                <span className="ml-1 text-ink-muted">
                  {w.llm_mode === 'live'
                    ? `Gemini via ${w.llm_provider === 'vertex' ? 'Vertex AI' : 'AI Studio'}`
                    : 'Recorded Gemini responses (no model cost)'}
                </span>
              </Row>
              <Row label="Models">
                <span className="font-mono text-[0.8125rem]">
                  {[w.models.flash, w.models.pro].filter(Boolean).join(' · ') ||
                    'Not configured (replay)'}
                </span>
              </Row>
              <Row label="AI budget today">
                <div className="max-w-sm space-y-1.5">
                  <Progress value={used} label="Share of today's AI budget used" />
                  <p className="text-xs text-ink-muted tabular-nums">
                    ₹{w.spent_today_inr.toFixed(2)} of ₹{String(w.daily_budget_inr)} used · live
                    calls stop at the cap
                  </p>
                </div>
              </Row>
              <Row label="Prompt versions">
                <div className="flex flex-wrap gap-1.5">
                  {w.prompt_versions.map((p) => (
                    <Badge key={p} className="font-mono">
                      {p}
                    </Badge>
                  ))}
                </div>
              </Row>
              <Row label="Build">
                <span className="font-mono text-[0.8125rem]">
                  {w.build_sha} · {w.environment}
                </span>
              </Row>
            </dl>
          </TabsContent>
        </Tabs>
      </Card>
    </div>
  );
}
