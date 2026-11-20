/** Routes. Every screen is a lazily loaded chunk; the shell and sign-in load first. */
import { FileQuestion } from 'lucide-react';
import { lazy, type ReactNode, Suspense } from 'react';
import { createBrowserRouter, Link, Navigate, useLocation, useRouteError } from 'react-router';

import { AppShell } from '@/app/AppShell';
import { EmptyState, ProblemAlert } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/primitives';
import { useSignedIn } from '@/lib/session';

const SignInPage = lazy(() => import('@/features/auth/SignInPage'));
const WorklistPage = lazy(() => import('@/features/claims/worklist/WorklistPage'));
const NewAuditPage = lazy(() => import('@/features/claims/new-audit/NewAuditPage'));
const WorkspacePage = lazy(() => import('@/features/claims/workspace/WorkspacePage'));
const AppealEditorPage = lazy(() => import('@/features/appeal/AppealEditorPage'));
const AppealsPage = lazy(() => import('@/features/appeal/AppealsPage'));
const AnalyticsPage = lazy(() => import('@/features/analytics/AnalyticsPage'));
const SettingsPage = lazy(() => import('@/features/settings/SettingsPage'));
const FamilyPage = lazy(() => import('@/features/family/FamilyPage'));
const CheckPage = lazy(() => import('@/features/family/CheckPage'));

function PageFallback() {
  return (
    <div className="space-y-4" role="status" aria-label="Loading">
      <Skeleton className="h-7 w-64" />
      <Skeleton className="h-4 w-96" />
      <div className="grid grid-cols-4 gap-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <Skeleton className="h-96" />
    </div>
  );
}

function page(node: ReactNode) {
  return <Suspense fallback={<PageFallback />}>{node}</Suspense>;
}

function RequireSession({ children }: { children: ReactNode }) {
  const signedIn = useSignedIn();
  const location = useLocation();
  if (!signedIn) return <Navigate to="/sign-in" replace state={{ from: location.pathname }} />;
  return children;
}

function RouteError() {
  const error = useRouteError();
  return (
    <div className="mx-auto max-w-xl p-10">
      <ProblemAlert
        error={error}
        onRetry={() => {
          window.location.reload();
        }}
      />
    </div>
  );
}

function NotFound() {
  return (
    <EmptyState
      icon={<FileQuestion aria-hidden />}
      title="Page not found"
      description="The link may be out of date, or the claim belongs to another hospital."
      action={
        <Button asChild>
          <Link to="/worklist">Back to the worklist</Link>
        </Button>
      }
    />
  );
}

export const router = createBrowserRouter([
  { path: '/sign-in', element: page(<SignInPage />), errorElement: <RouteError /> },
  // Public: the family's page (by link token) and the free check. No desk session.
  { path: '/f/:token', element: page(<FamilyPage />), errorElement: <RouteError /> },
  { path: '/check', element: page(<CheckPage />), errorElement: <RouteError /> },
  {
    path: '/',
    element: (
      <RequireSession>
        <AppShell />
      </RequireSession>
    ),
    errorElement: <RouteError />,
    children: [
      { index: true, element: <Navigate to="/worklist" replace /> },
      { path: 'worklist', element: page(<WorklistPage />) },
      { path: 'audits/new', element: page(<NewAuditPage />) },
      { path: 'claims/:claimId', element: page(<WorkspacePage />) },
      { path: 'claims/:claimId/appeal', element: page(<AppealEditorPage />) },
      { path: 'appeals', element: page(<AppealsPage />) },
      { path: 'analytics', element: page(<AnalyticsPage />) },
      { path: 'settings', element: page(<SettingsPage />) },
      { path: '*', element: <NotFound /> },
    ],
  },
]);
