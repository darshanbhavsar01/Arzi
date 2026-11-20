/**
 * The bill as the engine sees it. A person can correct a line's category, IRDAI list or amount,
 * or confirm a low-confidence line; each change re-runs only the deterministic rules (no model),
 * so totals update at once. E edits the amount of the focused row.
 */
import { Check, FileSearch, Pencil } from 'lucide-react';
import { type KeyboardEvent, useState } from 'react';
import { toast } from 'sonner';

import { ApiProblem } from '@/api/client';
import { useCorrectLine } from '@/api/queries';
import type { BillLine, ClaimRecord, LineCategory, LineCorrection } from '@/api/types';
import { ConfidenceMark, Money } from '@/components/domain';
import { Button } from '@/components/ui/button';
import { Badge, Input, Select } from '@/components/ui/primitives';
import { cn } from '@/lib/cn';
import { CATEGORY } from '@/lib/labels';

const LISTS = ['I', 'II', 'III', 'IV'] as const;

export function BillLinesTab({
  claim,
  onLine,
}: {
  claim: ClaimRecord;
  onLine: (line: BillLine) => void;
}) {
  const correct = useCorrectLine(claim.claim_id);
  const [editing, setEditing] = useState<number | null>(null);
  const [amount, setAmount] = useState('');
  const lines = claim.facts?.bill_lines ?? [];
  const outcomes = new Map((claim.audit?.lines ?? []).map((o) => [o.line_id, o]));
  const flagged = new Set(
    claim.issues
      .map((i) => i.line_id)
      .filter((id): id is number => id !== null && id !== undefined),
  );
  const editable = claim.status === 'audited';

  function save(line: BillLine, body: LineCorrection, what: string) {
    const started = performance.now();
    correct.mutate(
      { lineId: line.line_id, body },
      {
        onSuccess: () => {
          setEditing(null);
          toast.success(`Line ${String(line.line_id)} ${what}`, {
            description: `Rules re-run in ${String(Math.round(performance.now() - started))} ms. Totals updated.`,
          });
        },
        onError: (e) =>
          toast.error('Could not save the correction', {
            description: e instanceof ApiProblem ? e.detail : undefined,
          }),
      },
    );
  }

  function startEdit(line: BillLine) {
    if (!editable) return;
    setEditing(line.line_id);
    setAmount((line.amount / 100).toFixed(2));
  }

  function onRowKey(event: KeyboardEvent<HTMLTableRowElement>, line: BillLine) {
    if (event.target !== event.currentTarget) return;
    if (event.key.toLowerCase() === 'e') {
      event.preventDefault();
      startEdit(line);
    } else if (event.key === 'ArrowDown')
      (event.currentTarget.nextElementSibling as HTMLElement | null)?.focus();
    else if (event.key === 'ArrowUp')
      (event.currentTarget.previousElementSibling as HTMLElement | null)?.focus();
  }

  return (
    <div className="p-4">
      {!editable ? (
        <p className="mb-3 text-[0.8125rem] text-ink-muted">
          Lines are locked once an appeal is drafted; re-run the audit to correct them.
        </p>
      ) : (
        <p className="mb-3 text-xs text-ink-subtle">
          Focus a row and press E to edit its amount. Corrections re-run the rules only and are
          written to the audit log.
        </p>
      )}
      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full border-separate border-spacing-0 text-sm">
          <caption className="sr-only">Bill lines</caption>
          <thead className="bg-sunken text-xs text-ink-muted">
            <tr>
              {[
                '#',
                'Description',
                'Category',
                'IRDAI list',
                'Billed',
                'Qty',
                'Confidence',
                'Deducted',
                'Admissible',
                '',
              ].map((h, i) => (
                <th
                  key={h || i}
                  scope="col"
                  className={cn(
                    'border-b border-border px-3 py-2 font-medium whitespace-nowrap',
                    i >= 4 && i !== 6 && i !== 9 ? 'text-right' : 'text-left',
                  )}
                >
                  {h || <span className="sr-only">Actions</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => {
              const outcome = outcomes.get(line.line_id);
              const deducted =
                (outcome?.billed ?? line.amount) - (outcome?.admissible ?? line.amount);
              const needsConfirm =
                !line.confirmed_by_human && (line.confidence < 0.8 || flagged.has(line.line_id));
              return (
                <tr
                  key={line.line_id}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    onRowKey(e, line);
                  }}
                  className={cn(
                    'bg-surface focus-visible:outline-2 focus-visible:-outline-offset-2',
                    needsConfirm && 'bg-warning-bg/60',
                  )}
                >
                  <td className="border-b border-border px-3 py-2 tabular-nums text-ink-subtle">
                    {line.line_id}
                  </td>
                  <td className="min-w-52 border-b border-border px-3 py-2">
                    <button
                      type="button"
                      onClick={() => {
                        onLine(line);
                      }}
                      className="group inline-flex items-center gap-1.5 text-left hover:text-navy"
                      title="Show on the bill"
                    >
                      {line.description}
                      <FileSearch
                        className="size-3.5 text-ink-subtle opacity-0 group-hover:opacity-100"
                        aria-hidden
                      />
                    </button>
                    {line.confirmed_by_human ? (
                      <Badge tone="navy" className="ml-2">
                        Confirmed
                      </Badge>
                    ) : null}
                  </td>
                  <td className="border-b border-border px-3 py-1.5">
                    <Select
                      aria-label={`Category of line ${String(line.line_id)}`}
                      value={line.category}
                      disabled={!editable || correct.isPending}
                      onChange={(e) => {
                        save(line, { category: e.target.value as LineCategory }, 'recategorised');
                      }}
                      className="w-44"
                    >
                      {(Object.keys(CATEGORY) as LineCategory[]).map((c) => (
                        <option key={c} value={c}>
                          {CATEGORY[c]}
                        </option>
                      ))}
                    </Select>
                  </td>
                  <td className="border-b border-border px-3 py-1.5">
                    <Select
                      aria-label={`IRDAI list of line ${String(line.line_id)}`}
                      value={line.irdai_list ?? ''}
                      disabled={!editable || correct.isPending}
                      onChange={(e) => {
                        save(
                          line,
                          { irdai_list: (e.target.value || null) as (typeof LISTS)[number] | null },
                          'updated',
                        );
                      }}
                      className="w-24"
                    >
                      <option value="">None</option>
                      {LISTS.map((l) => (
                        <option key={l} value={l}>
                          List {l}
                        </option>
                      ))}
                    </Select>
                  </td>
                  <td className="border-b border-border px-3 py-1.5 text-right">
                    {editing === line.line_id ? (
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          save(line, { amount }, 'amount corrected');
                        }}
                        className="inline-flex items-center gap-1"
                      >
                        <Input
                          aria-label={`Amount of line ${String(line.line_id)} in rupees`}
                          value={amount}
                          onChange={(e) => {
                            setAmount(e.target.value);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Escape') setEditing(null);
                          }}
                          inputMode="decimal"
                          className="h-8 w-28 text-right tabular-nums"
                          ref={(node) => {
                            node?.focus();
                          }}
                        />
                        <Button
                          type="submit"
                          size="icon-sm"
                          aria-label="Save amount"
                          loading={correct.isPending}
                        >
                          <Check aria-hidden />
                        </Button>
                      </form>
                    ) : (
                      <span className="inline-flex items-center gap-1">
                        <Money paise={line.amount} exact />
                        {editable ? (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={`Edit amount of line ${String(line.line_id)}`}
                            onClick={() => {
                              startEdit(line);
                            }}
                          >
                            <Pencil aria-hidden />
                          </Button>
                        ) : null}
                      </span>
                    )}
                  </td>
                  <td className="border-b border-border px-3 py-2 text-right tabular-nums">
                    {line.qty}
                  </td>
                  <td className="border-b border-border px-3 py-2">
                    <ConfidenceMark value={line.confidence} />
                  </td>
                  <td className="border-b border-border px-3 py-2 text-right">
                    {deducted ? (
                      <Money paise={deducted} tone="risk" exact />
                    ) : (
                      <span className="text-ink-subtle">—</span>
                    )}
                  </td>
                  <td className="border-b border-border px-3 py-2 text-right">
                    <Money paise={outcome?.admissible ?? line.amount} exact />
                  </td>
                  <td className="border-b border-border px-3 py-1.5 text-right">
                    {needsConfirm && editable ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          save(line, {}, 'confirmed');
                        }}
                        disabled={correct.isPending}
                      >
                        Confirm
                      </Button>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
