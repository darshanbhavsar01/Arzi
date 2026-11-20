/**
 * Document upload with real progress. `fetch` cannot report upload progress, so this one call
 * uses XMLHttpRequest; errors still come back as `ApiProblem`s.
 */
import { API_BASE, ApiProblem, toProblem } from '@/api/client';
import type { DocType, DocumentOut } from '@/api/types';

export function uploadDocument(
  claimId: string,
  file: File,
  documentType: DocType | null,
  onProgress: (fraction: number) => void,
): Promise<DocumentOut> {
  const form = new FormData();
  form.append('file', file, file.name);
  if (documentType) form.append('document_type', documentType);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/claims/${claimId}/documents`);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onerror = () => {
      reject(ApiProblem.offline());
    };
    xhr.onload = () => {
      const response = new Response(xhr.responseText, {
        status: xhr.status,
        headers: { 'x-request-id': xhr.getResponseHeader('x-request-id') ?? '' },
      });
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(1);
        resolve(JSON.parse(xhr.responseText) as DocumentOut);
      } else {
        void toProblem(response).then(reject);
      }
    };
    xhr.send(form);
  });
}
