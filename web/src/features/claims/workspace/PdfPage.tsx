/**
 * One PDF page: canvas at device-pixel sharpness, fitted to the available width, with pdf.js's
 * transparent text layer on top so search terms (a bill line, a flagged item) can be highlighted.
 * pdf.js is loaded lazily, so screens without a document never download it.
 */
import type * as PdfJsModule from 'pdfjs-dist';
import { useEffect, useRef, useState } from 'react';

import { Skeleton } from '@/components/ui/primitives';

type PdfJs = typeof PdfJsModule;
type PdfDocument = Awaited<ReturnType<PdfJs['getDocument']>['promise']>;

let loader: Promise<PdfJs> | null = null;

export function loadPdfJs(): Promise<PdfJs> {
  loader ??= Promise.all([
    import('pdfjs-dist'),
    import('pdfjs-dist/build/pdf.worker.min.mjs?url'),
  ]).then(([pdfjs, worker]) => {
    pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
    return pdfjs;
  });
  return loader;
}

const documents = new Map<string, Promise<PdfDocument>>();

export function openPdf(url: string): Promise<PdfDocument> {
  let doc = documents.get(url);
  if (!doc) {
    doc = loadPdfJs().then((pdfjs) => pdfjs.getDocument({ url }).promise);
    documents.set(url, doc);
  }
  return doc;
}

function highlight(container: HTMLElement, query: string): HTMLElement | null {
  const words = query
    .toLowerCase()
    .split(/\s+/)
    .filter((w) => w.length > 2);
  let first: HTMLElement | null = null;
  container.querySelectorAll<HTMLElement>('span').forEach((span) => {
    const text = span.textContent.toLowerCase();
    const hit = words.length > 0 && words.every((w) => text.includes(w));
    span.classList.toggle('pdf-hit', hit);
    if (hit && !first) first = span;
  });
  return first;
}

export function PdfPage({
  url,
  page,
  query,
  label,
}: {
  url: string;
  page: number;
  query: string;
  label: string;
}) {
  const frame = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const text = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const node = frame.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.floor(entry.contentRect.width));
    });
    observer.observe(node);
    return () => {
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!width || !canvas.current || !text.current) return;
    let cancelled = false;
    // A function, not the variable: the cleanup flips it while this async work is suspended.
    const stopped = () => cancelled;
    const target = canvas.current;
    const layer = text.current;
    setReady(false);
    void (async () => {
      const [pdfjs, doc] = await Promise.all([loadPdfJs(), openPdf(url)]);
      const pdfPage = await doc.getPage(Math.min(page, doc.numPages));
      const base = pdfPage.getViewport({ scale: 1 });
      const scale = width / base.width;
      const viewport = pdfPage.getViewport({ scale });
      const ratio = window.devicePixelRatio || 1;
      target.width = Math.floor(viewport.width * ratio);
      target.height = Math.floor(viewport.height * ratio);
      target.style.width = `${String(Math.floor(viewport.width))}px`;
      target.style.height = `${String(Math.floor(viewport.height))}px`;
      const context = target.getContext('2d');
      if (!context || stopped()) return;
      await pdfPage.render({
        canvas: target,
        canvasContext: context,
        viewport,
        transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
      }).promise;
      if (stopped()) return;
      layer.replaceChildren();
      layer.style.setProperty('--scale-factor', String(scale));
      layer.style.setProperty('--total-scale-factor', String(scale));
      layer.style.setProperty('--scale-round-x', '1px');
      layer.style.setProperty('--scale-round-y', '1px');
      await new pdfjs.TextLayer({
        textContentSource: pdfPage.streamTextContent(),
        container: layer,
        viewport,
      }).render();
      if (stopped()) return;
      setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [url, page, width]);

  useEffect(() => {
    if (!ready || !text.current) return;
    const hit = highlight(text.current, query);
    hit?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [ready, query]);

  return (
    <div ref={frame} className="relative w-full">
      {!ready ? <Skeleton className="absolute inset-0 min-h-96" /> : null}
      <div
        role="img"
        aria-label={label}
        className="relative mx-auto w-fit overflow-hidden rounded-sm bg-white shadow-card ring-1 ring-border"
      >
        <canvas ref={canvas} aria-hidden />
        <div ref={text} className="pdf-text-layer" />
      </div>
    </div>
  );
}
