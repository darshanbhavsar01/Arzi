/**
 * Typed fetch wrapper. Every failure becomes an `ApiProblem` carrying the RFC 7807 fields and the
 * request ID, so error states can show what went wrong and a reference support can trace.
 */

export const API_BASE = '/api/v1';

export class ApiProblem extends Error {
  constructor(
    readonly status: number,
    readonly slug: string,
    readonly title: string,
    readonly detail: string,
    readonly requestId: string | null,
  ) {
    super(detail || title);
    this.name = 'ApiProblem';
  }

  static offline(): ApiProblem {
    return new ApiProblem(
      0,
      'network-error',
      'Cannot reach Arzi',
      'Check the connection and try again.',
      null,
    );
  }
}

interface ProblemBody {
  type?: string;
  title?: string;
  detail?: unknown;
  request_id?: string;
}

export async function toProblem(response: Response): Promise<ApiProblem> {
  const requestId = response.headers.get('x-request-id');
  let body: ProblemBody = {};
  try {
    body = (await response.json()) as ProblemBody;
  } catch {
    // Not JSON (a proxy error page); fall back to the status line.
  }
  const slug = body.type?.split('/').pop() ?? `http-${String(response.status)}`;
  const detail = typeof body.detail === 'string' ? body.detail : '';
  return new ApiProblem(
    response.status,
    slug,
    body.title ?? response.statusText,
    detail,
    body.request_id ?? requestId,
  );
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH';
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal | undefined;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json', ...options.headers };
  const init: RequestInit = { method: options.method ?? 'GET', headers };
  if (options.signal) init.signal = options.signal;
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(options.body);
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw ApiProblem.offline();
  }
  if (!response.ok) throw await toProblem(response);
  return (await response.json()) as T;
}

/** A fresh key per user action, so a double click never starts (or pays for) two runs. */
export function idempotencyKey(): string {
  return crypto.randomUUID();
}
