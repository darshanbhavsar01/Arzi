/** Drag-and-drop document picker with per-file type, progress and a required-documents checklist. */
import { CheckCircle2, Circle, FileImage, FileText, UploadCloud, X } from 'lucide-react';
import { type DragEvent, useId, useRef, useState } from 'react';

import type { ClaimMode, DocType } from '@/api/types';
import { Button } from '@/components/ui/button';
import { Progress, Select } from '@/components/ui/primitives';
import { cn } from '@/lib/cn';
import { DOC_TYPE } from '@/lib/labels';
import {
  coverage,
  formatSize,
  type PickedFile,
  rejectReason,
  requirements,
} from '@/features/claims/new-audit/files';

export function FilePicker({
  mode,
  files,
  onAdd,
  onRemove,
  onType,
  locked,
}: {
  mode: ClaimMode;
  files: PickedFile[];
  onAdd: (files: File[]) => void;
  onRemove: (id: string) => void;
  onType: (id: string, type: DocType | null) => void;
  locked: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const hintId = useId();
  const covered = coverage(mode, files);

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setOver(false);
    if (!locked) onAdd(Array.from(event.dataTransfer.files));
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
      <div className="space-y-4">
        {/* Drop target only; the "Choose files" button inside is the keyboard and screen-reader path. */}
        {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => {
            setOver(false);
          }}
          onDrop={drop}
          className={cn(
            'flex flex-col items-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors',
            over ? 'border-navy bg-navy-soft' : 'border-border-strong bg-canvas',
            locked && 'opacity-60',
          )}
        >
          <UploadCloud className="size-8 text-accent" aria-hidden />
          <p className="mt-3 font-medium">Drop the claim documents here</p>
          <p id={hintId} className="mt-1 text-[0.8125rem] text-ink-muted">
            PDF, JPEG or PNG, up to 20 MB each. A phone photo of the bill works.
          </p>
          <Button
            variant="secondary"
            className="mt-4"
            disabled={locked}
            onClick={() => input.current?.click()}
            aria-describedby={hintId}
          >
            Choose files
          </Button>
          <input
            ref={input}
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
            className="sr-only"
            tabIndex={-1}
            aria-hidden
            onChange={(e) => {
              onAdd(Array.from(e.target.files ?? []));
              e.target.value = '';
            }}
          />
        </div>

        {files.length ? (
          <ul
            className="divide-y divide-border rounded-xl border border-border bg-surface"
            aria-label="Documents to upload"
          >
            {files.map((f) => {
              const Icon = f.file.type.startsWith('image/') ? FileImage : FileText;
              const problem = f.error ?? rejectReason(f.file);
              return (
                <li key={f.id} className="flex items-center gap-3 px-4 py-3">
                  <Icon className="size-5 shrink-0 text-ink-subtle" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <p className="truncate font-medium">{f.file.name}</p>
                      <span className="shrink-0 text-xs text-ink-subtle">
                        {formatSize(f.file.size)}
                      </span>
                    </div>
                    {problem ? (
                      <p className="text-xs text-danger">{problem}</p>
                    ) : f.state === 'uploading' || f.state === 'uploaded' ? (
                      <Progress
                        value={f.progress}
                        label={`Uploading ${f.file.name}`}
                        className="mt-1.5"
                      />
                    ) : null}
                  </div>
                  <Select
                    aria-label={`Document type for ${f.file.name}`}
                    value={f.type ?? ''}
                    disabled={locked}
                    onChange={(e) => {
                      onType(f.id, (e.target.value || null) as DocType | null);
                    }}
                    className="w-48 shrink-0"
                  >
                    <option value="">Detect automatically</option>
                    {(Object.keys(DOC_TYPE) as DocType[]).map((t) => (
                      <option key={t} value={t}>
                        {DOC_TYPE[t]}
                      </option>
                    ))}
                  </Select>
                  {f.state === 'uploaded' ? (
                    <CheckCircle2 className="size-5 shrink-0 text-success" aria-label="Uploaded" />
                  ) : (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      disabled={locked}
                      onClick={() => {
                        onRemove(f.id);
                      }}
                      aria-label={`Remove ${f.file.name}`}
                    >
                      <X aria-hidden />
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>

      <aside
        aria-label="Documents this audit needs"
        className="rounded-xl border border-border bg-surface p-4"
      >
        <p className="text-sm font-semibold">This audit needs</p>
        <ul className="mt-3 space-y-2.5">
          {requirements(mode).map((r) => {
            const ok = covered.get(r.id) ?? false;
            return (
              <li key={r.id} className="flex items-start gap-2 text-[0.8125rem]">
                {ok ? (
                  <CheckCircle2 className="mt-px size-4 shrink-0 text-success" aria-hidden />
                ) : (
                  <Circle className="mt-px size-4 shrink-0 text-border-strong" aria-hidden />
                )}
                <span className={ok ? 'text-ink' : 'text-ink-muted'}>
                  {r.label}
                  {r.required ? null : <span className="text-ink-subtle"> · recommended</span>}
                  <span className="sr-only">{ok ? ', added' : ', not added yet'}</span>
                </span>
              </li>
            );
          })}
        </ul>
        <p className="mt-4 text-xs text-ink-subtle">
          Ticks follow file names; Arzi reads every page and confirms the type during the audit.
        </p>
      </aside>
    </div>
  );
}
