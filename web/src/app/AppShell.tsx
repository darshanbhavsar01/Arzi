/**
 * The desk layout: collapsible sidebar, top bar (hospital, data and AI mode, ⌘K search, user
 * menu) and the persistent human-review footer. Pages render into the outlet.
 */
import {
  ChevronsLeft,
  ChevronsRight,
  FilePlus2,
  ListChecks,
  LogOut,
  Scale,
  Search,
  Settings2,
} from 'lucide-react';
import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router';

import { useWorkspace } from '@/api/queries';
import { CommandPalette, useCommandPalette } from '@/app/CommandPalette';
import { ArziMark, ArziWordmark } from '@/components/brand';
import { Button } from '@/components/ui/button';
import {
  Menu,
  MenuContent,
  MenuItem,
  MenuLabel,
  MenuSeparator,
  MenuTrigger,
  Tooltip,
} from '@/components/ui/overlays';
import { Badge, Kbd } from '@/components/ui/primitives';
import { cn } from '@/lib/cn';
import { preference, setPreference, signOut } from '@/lib/session';

const NAV = [
  { to: '/worklist', label: 'Worklist', icon: ListChecks },
  { to: '/audits/new', label: 'New audit', icon: FilePlus2 },
  { to: '/appeals', label: 'Appeals', icon: Scale },
  { to: '/settings', label: 'Settings', icon: Settings2 },
] as const;

const ROLE: Record<string, string> = {
  billing_executive: 'Billing executive',
  reviewer: 'Reviewer',
  admin: 'Administrator',
};

export function AppShell() {
  const [collapsed, setCollapsed] = useState(() => preference('sidebar-collapsed', false));
  const palette = useCommandPalette();
  const { data: workspace } = useWorkspace();
  const navigate = useNavigate();
  const isMac = navigator.userAgent.includes('Mac');
  const initials = (workspace?.user_name ?? 'Desk')
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="flex min-h-screen bg-canvas">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:shadow-pop"
      >
        Skip to content
      </a>
      <aside
        className={cn(
          'sticky top-0 flex h-screen shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-200',
          collapsed ? 'w-16' : 'w-60',
        )}
      >
        <div
          className={cn(
            'flex h-14 items-center gap-2 border-b border-border',
            collapsed ? 'justify-center' : 'px-4',
          )}
        >
          <ArziMark className="size-8" />
          {collapsed ? null : <ArziWordmark />}
        </div>
        <nav aria-label="Main" className="flex-1 space-y-0.5 p-2">
          {NAV.map(({ to, label, icon: Icon }) => {
            const link = (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    'flex h-9 items-center gap-3 rounded-md px-3 text-sm font-medium text-ink-muted hover:bg-sunken hover:text-ink',
                    isActive && 'bg-navy-soft text-navy',
                    collapsed && 'justify-center px-0',
                  )
                }
                aria-label={collapsed ? label : undefined}
              >
                <Icon className="size-4 shrink-0" aria-hidden />
                {collapsed ? null : label}
              </NavLink>
            );
            return collapsed ? (
              <Tooltip key={to} content={label} side="right">
                {link}
              </Tooltip>
            ) : (
              link
            );
          })}
        </nav>
        <div className="border-t border-border p-2">
          <Button
            variant="ghost"
            size="sm"
            className={cn('w-full', collapsed ? 'justify-center px-0' : 'justify-start')}
            onClick={() => {
              setCollapsed((c) => {
                setPreference('sidebar-collapsed', !c);
                return !c;
              });
            }}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? (
              <ChevronsRight aria-hidden />
            ) : (
              <>
                <ChevronsLeft aria-hidden /> Collapse
              </>
            )}
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-surface/95 px-6 backdrop-blur">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">
              {workspace?.hospital?.name ?? 'Hospital workspace'}
            </p>
            <p className="truncate text-xs text-ink-subtle">
              {workspace?.hospital?.city ?? ' '} · TPA desk
            </p>
          </div>
          <Badge tone="warning" className="ml-1 hidden md:inline-flex">
            Synthetic data
          </Badge>
          {workspace ? (
            <Tooltip
              content={
                workspace.llm_mode === 'live'
                  ? 'Gemini on Vertex AI, budget-guarded'
                  : 'Model answers served from recorded Gemini responses'
              }
            >
              <Badge
                tone={workspace.llm_mode === 'live' ? 'success' : 'info'}
                tabIndex={0}
                className="hidden md:inline-flex"
              >
                AI:{' '}
                {workspace.llm_mode === 'live'
                  ? 'Live'
                  : workspace.llm_mode === 'replay'
                    ? 'Replay'
                    : 'Fake'}
              </Badge>
            </Tooltip>
          ) : null}
          <div className="flex-1" />
          <button
            type="button"
            onClick={() => {
              palette.setOpen(true);
            }}
            className="hidden h-9 w-72 items-center gap-2 rounded-md border border-border-strong bg-canvas px-3 text-sm text-ink-subtle hover:border-ink-subtle lg:flex"
          >
            <Search className="size-4" aria-hidden />
            Search claims and screens
            <span className="ml-auto flex gap-0.5">
              <Kbd>{isMac ? '⌘' : 'Ctrl'}</Kbd>
              <Kbd>K</Kbd>
            </span>
          </button>
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label="Search"
            onClick={() => {
              palette.setOpen(true);
            }}
          >
            <Search aria-hidden />
          </Button>
          <Menu>
            <MenuTrigger asChild>
              <button
                type="button"
                className="grid size-9 place-content-center rounded-full bg-navy text-xs font-semibold text-white"
              >
                {/* The visible initials start the accessible name, so voice control can say them. */}
                {initials}
                <span className="sr-only"> account menu</span>
              </button>
            </MenuTrigger>
            <MenuContent>
              <MenuLabel>
                <span className="block text-sm font-medium text-ink">
                  {workspace?.user_name ?? 'Demo desk'}
                </span>
                {ROLE[workspace?.user_role ?? ''] ?? 'Desk user'}
              </MenuLabel>
              <MenuSeparator />
              <MenuItem
                onSelect={() => {
                  void navigate('/settings');
                }}
              >
                <Settings2 aria-hidden /> Settings
              </MenuItem>
              <MenuItem
                onSelect={() => {
                  signOut();
                  void navigate('/sign-in');
                }}
              >
                <LogOut aria-hidden /> Sign out
              </MenuItem>
            </MenuContent>
          </Menu>
        </header>

        <main id="main" className="flex-1 px-6 py-6">
          <Outlet />
        </main>
        <footer className="border-t border-border px-6 py-3 text-xs text-ink-subtle">
          Arzi is decision support. A qualified person reviews and signs every appeal.
        </footer>
      </div>
      <CommandPalette open={palette.open} onOpenChange={palette.setOpen} />
    </div>
  );
}
