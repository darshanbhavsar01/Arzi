/**
 * The source documents beside the findings. Clicking a flag or a bill line focuses the bill on
 * the line's page and highlights its text, so every number can be checked against the paper.
 */
import { ChevronLeft, ChevronRight, FileImage, FileText, Search } from 'lucide-react';
import { useState } from 'react';

import { documentUrl } from '@/api/queries';
import type { DocType, DocumentOut } from '@/api/types';
import { Button } from '@/components/ui/button';
import { Input, Select } from '@/components/ui/primitives';
import { DOC_TYPE } from '@/lib/labels';
import { openPdf, PdfPage } from '@/features/claims/workspace/PdfPage';

export interface DocumentFocus {
  documentType: DocType;
  page: number;
  query: string;
  nonce: number;
}

const ORDER: DocType[] = [
  'itemised_bill',
  'insurer_letter',
  'policy_schedule',
  'policy_wording',
  'discharge_summary',
  'investigation_report',
  'implant_invoice',
  'other',
];

function rank(doc: DocumentOut): number {
  const i = ORDER.indexOf(doc.document_type ?? 'other');
  return i < 0 ? ORDER.length : i;
}

export function DocumentViewer({
  claimId,
  documents,
  focus,
}: {
  claimId: string;
  documents: DocumentOut[];
  focus: DocumentFocus | null;
}) {
  const sorted = [...documents].sort((a, b) => rank(a) - rank(b));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Until someone picks a document, follow the preferred order (bill first), which settles once
  // the audit has classified every upload.
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState('');
  const [draft, setDraft] = useState('');
  const [searching, setSearching] = useState(false);
  const [notFound, setNotFound] = useState(false);

  const [seenFocus, setSeenFocus] = useState<number | null>(null);

  // A new focus request (a clicked flag or bill line) moves the viewer; adjusting state while
  // rendering, as React recommends for responding to a changed prop.
  if (focus && focus.nonce !== seenFocus) {
    setSeenFocus(focus.nonce);
    const target = sorted.find((d) => d.document_type === focus.documentType);
    if (target) setSelectedId(target.document_id);
    setPage(focus.page);
    setQuery(focus.query);
    setDraft(focus.query);
  }

  const selected = sorted.find((d) => d.document_id === selectedId) ?? sorted[0];

  if (!selected) {
    return <p className="p-6 text-ink-muted">No documents on this claim yet.</p>;
  }
  const url = documentUrl(claimId, selected.document_id);
  const isPdf = selected.content_type === 'application/pdf';

  async function search() {
    const term = draft.trim();
    setQuery(term);
    setNotFound(false);
    if (!term || !isPdf) return;
    setSearching(true);
    try {
      const doc = await openPdf(url);
      for (let n = 1; n <= doc.numPages; n += 1) {
        const content = await (await doc.getPage(n)).getTextContent();
        const text = content.items
          .map((i) => ('str' in i ? i.str : ''))
          .join(' ')
          .toLowerCase();
        if (
          term
            .toLowerCase()
            .split(/\s+/)
            .every((w) => text.includes(w))
        ) {
          setPage(n);
          return;
        }
      }
      setNotFound(true);
    } finally {
      setSearching(false);
    }
  }

  return (
    <section aria-label="Source documents" className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        <Select
          aria-label="Document"
          value={selected.document_id}
          onChange={(e) => {
            setSelectedId(e.target.value);
            setPage(1);
            setQuery('');
            setDraft('');
          }}
          className="min-w-0 flex-1"
        >
          {sorted.map((d) => (
            <option key={d.document_id} value={d.document_id}>
              {d.document_type ? DOC_TYPE[d.document_type] : 'Unclassified'} · {d.filename}
            </option>
          ))}
        </Select>
        <form
          role="search"
          className="relative w-44"
          onSubmit={(e) => {
            e.preventDefault();
            void search();
          }}
        >
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-ink-subtle"
            aria-hidden
          />
          <Input
            aria-label="Find in document"
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
            }}
            placeholder="Find text"
            className="pl-8"
            disabled={!isPdf || searching}
          />
        </form>
      </div>
      <div className="flex items-center justify-between gap-2 border-b border-border bg-canvas px-3 py-1.5 text-xs text-ink-muted">
        <span className="inline-flex items-center gap-1.5">
          {isPdf ? (
            <FileText className="size-3.5" aria-hidden />
          ) : (
            <FileImage className="size-3.5" aria-hidden />
          )}
          {selected.pages} {selected.pages === 1 ? 'page' : 'pages'}
          {notFound ? <span className="text-warning">· “{query}” not found</span> : null}
        </span>
        {selected.pages > 1 ? (
          <span className="inline-flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Previous page"
              disabled={page <= 1}
              onClick={() => {
                setPage(page - 1);
              }}
            >
              <ChevronLeft aria-hidden />
            </Button>
            <span className="tabular-nums" aria-live="polite">
              Page {page} of {selected.pages}
            </span>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Next page"
              disabled={page >= selected.pages}
              onClick={() => {
                setPage(page + 1);
              }}
            >
              <ChevronRight aria-hidden />
            </Button>
          </span>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 overflow-auto bg-sunken p-4">
        {isPdf ? (
          <PdfPage
            url={url}
            page={page}
            query={query}
            label={`${selected.filename}, page ${String(page)}`}
          />
        ) : (
          <img
            src={url}
            alt={`${selected.filename} (photographed document)`}
            className="mx-auto w-full max-w-3xl rounded-sm shadow-card ring-1 ring-border"
            loading="lazy"
          />
        )}
      </div>
    </section>
  );
}
