/**
 * The letter, section by section. Read mode shows rendered text with locked amount chips; edit
 * mode shows each section's template, where amounts stay placeholders the editor inserts from a
 * menu (Arzi fills them from the rules engine, and the server rejects typed amounts).
 */
import { IndianRupee } from 'lucide-react';
import { useRef } from 'react';

import type { AppealVersion, PolicyClause } from '@/api/types';
import { CitationChip } from '@/components/CitationChip';
import { Money } from '@/components/domain';
import { Button } from '@/components/ui/button';
import { Menu, MenuContent, MenuItem, MenuLabel, MenuTrigger } from '@/components/ui/overlays';
import { Textarea } from '@/components/ui/primitives';
import { cn } from '@/lib/cn';
import { formatMoney } from '@/lib/format';
import { ruleTitle } from '@/lib/labels';
import { type PlaceholderOption, WithLockedAmounts } from '@/features/appeal/appealText';

export interface AppealDraftState {
  subject: string;
  facts: string;
  relief: string;
  arguments: Record<string, string>;
}

export function draftFrom(appeal: AppealVersion): AppealDraftState {
  const c = appeal.content;
  return {
    subject: c.subject.template,
    facts: c.facts.template,
    relief: c.relief.template,
    arguments: Object.fromEntries(c.items.map((i) => [i.flag_id, i.argument.template])),
  };
}

function SectionText({
  id,
  label,
  rendered,
  template,
  editing,
  onChange,
  options,
  rows = 3,
}: {
  id: string;
  label: string;
  rendered: string | null | undefined;
  template: string;
  editing: boolean;
  onChange: (value: string) => void;
  options: PlaceholderOption[];
  rows?: number;
}) {
  const area = useRef<HTMLTextAreaElement>(null);

  function insert(token: string) {
    const node = area.current;
    const at = node?.selectionStart ?? template.length;
    const end = node?.selectionEnd ?? at;
    onChange(`${template.slice(0, at)}${token}${template.slice(end)}`);
    requestAnimationFrame(() => {
      node?.focus();
      node?.setSelectionRange(at + token.length, at + token.length);
    });
  }

  if (!editing) {
    return rendered ? (
      <p className="leading-relaxed whitespace-pre-line">{WithLockedAmounts({ text: rendered })}</p>
    ) : (
      <p className="rounded-md border border-dashed border-warning-border bg-warning-bg/50 px-3 py-2 text-[0.8125rem] text-warning">
        {template
          ? 'This section did not pass the checks. Edit it to continue.'
          : 'Not written yet. Edit to add this section.'}
      </p>
    );
  }
  return (
    <div className="space-y-1.5">
      <Textarea
        id={id}
        ref={area}
        value={template}
        rows={rows}
        onChange={(e) => {
          onChange(e.target.value);
        }}
        aria-label={label}
        className="font-[inherit]"
      />
      <Menu>
        <MenuTrigger asChild>
          <Button variant="ghost" size="sm">
            <IndianRupee aria-hidden />
            Insert amount
          </Button>
        </MenuTrigger>
        <MenuContent align="start" className="w-80">
          <MenuLabel>Amounts from the rules engine</MenuLabel>
          {options.map((o) => (
            <MenuItem
              key={o.token}
              onSelect={() => {
                insert(o.token);
              }}
            >
              <span className="flex-1 truncate">{o.label}</span>
              <span className="tabular-nums text-ink-muted">{formatMoney(o.value)}</span>
            </MenuItem>
          ))}
        </MenuContent>
      </Menu>
    </div>
  );
}

export function AppealSections({
  appeal,
  draft,
  editing,
  onChange,
  options,
  clauses,
  errors,
}: {
  appeal: AppealVersion;
  draft: AppealDraftState;
  editing: boolean;
  onChange: (next: AppealDraftState) => void;
  options: PlaceholderOption[];
  clauses: PolicyClause[];
  errors: string[];
}) {
  const c = appeal.content;
  const has = (field: string) => errors.some((e) => e.includes(field));
  return (
    <div className="space-y-6">
      <section
        aria-labelledby="sec-subject"
        className={cn(has('subject') && 'rounded-lg ring-2 ring-danger-border')}
      >
        <h2
          id="sec-subject"
          className="mb-1.5 text-xs font-semibold tracking-wide text-ink-subtle uppercase"
        >
          Subject
        </h2>
        <SectionText
          id="subject"
          label="Subject"
          rendered={c.subject.text}
          template={draft.subject}
          editing={editing}
          options={options}
          rows={1}
          onChange={(subject) => {
            onChange({ ...draft, subject });
          }}
        />
      </section>
      <section
        aria-labelledby="sec-facts"
        className={cn(has('facts') && 'rounded-lg ring-2 ring-danger-border')}
      >
        <h2
          id="sec-facts"
          className="mb-1.5 text-xs font-semibold tracking-wide text-ink-subtle uppercase"
        >
          Facts
        </h2>
        <SectionText
          id="facts"
          label="Facts"
          rendered={c.facts.text}
          template={draft.facts}
          editing={editing}
          options={options}
          rows={4}
          onChange={(facts) => {
            onChange({ ...draft, facts });
          }}
        />
      </section>
      <section aria-labelledby="sec-items">
        <h2
          id="sec-items"
          className="mb-2 text-xs font-semibold tracking-wide text-ink-subtle uppercase"
        >
          Items in dispute
        </h2>
        <ol className="space-y-3">
          {c.items.map((item, i) => (
            <li
              key={item.flag_id}
              className={cn(
                'rounded-xl border border-border bg-canvas p-4',
                has(`arguments[${item.flag_id}]`) && 'ring-2 ring-danger-border',
              )}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <p className="font-semibold">
                  {i + 1}. {ruleTitle(item.rule_id)}
                </p>
                <span
                  className="inline-flex items-center gap-1.5 rounded-md bg-navy-soft px-2 py-0.5 text-navy"
                  title="Amount from the rules engine, locked"
                >
                  <Money paise={item.amount} exact className="font-semibold" />
                </span>
              </div>
              <p className="mt-1 text-[0.8125rem] text-ink-muted">
                <span className="font-medium text-ink">Insurer’s reason:</span>{' '}
                {item.insurer_reason}
              </p>
              <div className="mt-3">
                <p className="mb-1 text-[0.8125rem] font-medium">Our grounds</p>
                <SectionText
                  id={`arg-${item.flag_id}`}
                  label={`Grounds for ${ruleTitle(item.rule_id)}`}
                  rendered={item.argument.text}
                  template={draft.arguments[item.flag_id] ?? ''}
                  editing={editing}
                  options={options}
                  rows={5}
                  onChange={(value) => {
                    onChange({
                      ...draft,
                      arguments: { ...draft.arguments, [item.flag_id]: value },
                    });
                  }}
                />
              </div>
              {item.citations.length ? (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {item.citations.map((ref) => (
                    <CitationChip key={ref} refId={ref} clauses={clauses} />
                  ))}
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      </section>
      <section
        aria-labelledby="sec-relief"
        className={cn(has('relief') && 'rounded-lg ring-2 ring-danger-border')}
      >
        <h2
          id="sec-relief"
          className="mb-1.5 text-xs font-semibold tracking-wide text-ink-subtle uppercase"
        >
          Relief sought
        </h2>
        <SectionText
          id="relief"
          label="Relief sought"
          rendered={c.relief.text}
          template={draft.relief}
          editing={editing}
          options={options}
          rows={3}
          onChange={(relief) => {
            onChange({ ...draft, relief });
          }}
        />
      </section>
    </div>
  );
}
