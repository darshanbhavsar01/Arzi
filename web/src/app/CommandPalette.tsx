/** ⌘K / Ctrl+K: jump to any screen or claim, or load the demo cases, from the keyboard. */
import { Command } from 'cmdk';
import { Dialog as DialogPrimitive } from 'radix-ui';
import {
  FilePlus2,
  FolderOpen,
  ListChecks,
  Scale,
  Search,
  Settings2,
  Sparkles,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';

import { useClaims, useLoadDemo, useWorkspace } from '@/api/queries';
import { MODE } from '@/lib/labels';

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === 'k' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, []);
  return { open, setOpen };
}

const item =
  'flex cursor-default items-center gap-3 rounded-md px-3 py-2 text-sm text-ink data-[selected=true]:bg-sunken [&_svg]:size-4 [&_svg]:text-ink-subtle';

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const navigate = useNavigate();
  const { data } = useClaims({});
  const { data: workspace } = useWorkspace();
  const demo = useLoadDemo();

  const go = (path: string) => {
    onOpenChange(false);
    void navigate(path);
  };

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-navy/40 animate-fade-in" />
        <DialogPrimitive.Content className="fixed top-[18vh] left-1/2 z-50 w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-surface shadow-pop animate-fade-in">
          <DialogPrimitive.Title className="sr-only">Search Arzi</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            Type a claim ID, patient pseudonym, insurer or screen name.
          </DialogPrimitive.Description>
          <Command label="Search Arzi" loop>
            <div className="flex items-center gap-2 border-b border-border px-4">
              <Search className="size-4 text-ink-subtle" aria-hidden />
              <Command.Input
                placeholder="Search claims, patients, screens…"
                className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-ink-subtle"
              />
            </div>
            <Command.List className="max-h-[50vh] overflow-y-auto p-2">
              <Command.Empty className="px-3 py-6 text-center text-ink-muted">
                No matches.
              </Command.Empty>
              <Command.Group
                heading="Go to"
                className="text-xs text-ink-subtle [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5"
              >
                <Command.Item
                  className={item}
                  onSelect={() => {
                    go('/worklist');
                  }}
                >
                  <ListChecks aria-hidden /> Worklist
                </Command.Item>
                <Command.Item
                  className={item}
                  onSelect={() => {
                    go('/audits/new');
                  }}
                >
                  <FilePlus2 aria-hidden /> New audit
                </Command.Item>
                <Command.Item
                  className={item}
                  onSelect={() => {
                    go('/appeals');
                  }}
                >
                  <Scale aria-hidden /> Appeals
                </Command.Item>
                <Command.Item
                  className={item}
                  onSelect={() => {
                    go('/settings');
                  }}
                >
                  <Settings2 aria-hidden /> Settings
                </Command.Item>
                {workspace?.demo_cases_available ? (
                  <Command.Item
                    className={item}
                    onSelect={() => {
                      onOpenChange(false);
                      demo.mutate(undefined, {
                        onSuccess: () =>
                          toast.success('Demo cases loaded', {
                            description: 'Cases A, B and C are being audited.',
                          }),
                        onError: () => toast.error('Could not load the demo cases'),
                      });
                    }}
                  >
                    <Sparkles aria-hidden /> Load demo cases A, B and C
                  </Command.Item>
                ) : null}
              </Command.Group>
              {data?.items.length ? (
                <Command.Group
                  heading="Claims"
                  className="text-xs text-ink-subtle [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5"
                >
                  {data.items.map((claim) => (
                    <Command.Item
                      key={claim.claim_id}
                      value={`${claim.claim_id} ${claim.patient ?? ''} ${claim.insurer ?? ''}`}
                      className={item}
                      onSelect={() => {
                        go(`/claims/${claim.claim_id}`);
                      }}
                    >
                      <FolderOpen aria-hidden />
                      <span className="font-mono text-[0.8125rem]">{claim.claim_id}</span>
                      <span className="truncate text-ink-muted">
                        {claim.patient ?? 'Not audited yet'} · {MODE[claim.mode].short}
                      </span>
                    </Command.Item>
                  ))}
                </Command.Group>
              ) : null}
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
