/** Providers: server state (TanStack Query), tooltips, toasts, and the router. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router';
import { Toaster } from 'sonner';

import { ApiProblem } from '@/api/client';
import { router } from '@/app/router';
import { TooltipProvider } from '@/components/ui/overlays';

function retry(failures: number, error: unknown): boolean {
  // Retry only what retrying can fix: the network or a server error. Never a 4xx.
  const transient = !(error instanceof ApiProblem) || error.status === 0 || error.status >= 500;
  return transient && failures < 2;
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry, staleTime: 15_000, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

const queryClient = makeQueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={250}>
        <RouterProvider router={router} />
        <Toaster
          position="bottom-right"
          toastOptions={{
            classNames: {
              toast: 'border border-border bg-surface text-ink shadow-pop font-sans',
              description: 'text-ink-muted',
            },
          }}
        />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
