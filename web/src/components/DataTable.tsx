/**
 * The desk's table: sortable headers (with `aria-sort`), column visibility, comfortable/compact
 * density, sticky header, and keyboard row navigation (↑/↓ move, Enter opens).
 */
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  type SortingState,
  useReactTable,
  type VisibilityState,
} from '@tanstack/react-table';
import { ArrowDown, ArrowUp, ChevronsUpDown, Columns3, Rows3 } from 'lucide-react';
import { type KeyboardEvent, type ReactNode, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Menu, MenuContent, MenuLabel, MenuTrigger } from '@/components/ui/overlays';
import { Checkbox } from '@/components/ui/primitives';
import { cn } from '@/lib/cn';

export interface ColumnMeta {
  align?: 'left' | 'right';
  label?: string;
}

interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T>[];
  caption: string;
  onOpen?: (row: T) => void;
  initialSorting?: SortingState;
  toolbar?: ReactNode;
  getRowId: (row: T) => string;
  rowClassName?: (row: T) => string | undefined;
}

export function DataTable<T>({
  data,
  columns,
  caption,
  onOpen,
  initialSorting = [],
  toolbar,
  getRowId,
  rowClassName,
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting);
  const [visibility, setVisibility] = useState<VisibilityState>({});
  const [compact, setCompact] = useState(false);
  const body = useRef<HTMLTableSectionElement>(null);

  // TanStack Table returns non-memoisable functions by design; the React Compiler skips it.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data,
    columns,
    state: { sorting, columnVisibility: visibility },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId,
  });

  function onRowKey(event: KeyboardEvent<HTMLTableRowElement>, row: T) {
    const rows = Array.from(body.current?.querySelectorAll<HTMLTableRowElement>('tr') ?? []);
    const index = rows.indexOf(event.currentTarget);
    if (event.key === 'ArrowDown') rows[index + 1]?.focus();
    else if (event.key === 'ArrowUp') rows[index - 1]?.focus();
    else if (event.key === 'Enter' && onOpen) onOpen(row);
    else return;
    event.preventDefault();
  }

  const hideable = table.getAllLeafColumns().filter((c) => c.getCanHide());

  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <div className="flex flex-1 flex-wrap items-center gap-2">{toolbar}</div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-pressed={compact}
            aria-label={compact ? 'Comfortable rows' : 'Compact rows'}
            onClick={() => {
              setCompact((c) => !c);
            }}
          >
            <Rows3 aria-hidden />
          </Button>
          <Menu>
            <MenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Choose columns">
                <Columns3 aria-hidden />
              </Button>
            </MenuTrigger>
            <MenuContent>
              <MenuLabel>Columns</MenuLabel>
              {hideable.map((column) => {
                const meta = column.columnDef.meta as ColumnMeta | undefined;
                const id = `column-${column.id}`;
                return (
                  <label
                    key={column.id}
                    htmlFor={id}
                    className="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm hover:bg-sunken"
                  >
                    <Checkbox
                      id={id}
                      checked={column.getIsVisible()}
                      onCheckedChange={(v) => {
                        column.toggleVisibility(v === true);
                      }}
                    />
                    {meta?.label ?? column.id}
                  </label>
                );
              })}
            </MenuContent>
          </Menu>
        </div>
      </div>
      <div className="min-h-0 overflow-auto">
        <table className="w-full border-separate border-spacing-0 text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="sticky top-0 z-10 bg-sunken">
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  const meta = header.column.columnDef.meta as ColumnMeta | undefined;
                  const sorted = header.column.getIsSorted();
                  const canSort = header.column.getCanSort();
                  const content = flexRender(header.column.columnDef.header, header.getContext());
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      aria-sort={
                        sorted === 'asc'
                          ? 'ascending'
                          : sorted === 'desc'
                            ? 'descending'
                            : undefined
                      }
                      className={cn(
                        'border-b border-border px-4 py-2 text-xs font-medium whitespace-nowrap text-ink-muted',
                        meta?.align === 'right' ? 'text-right' : 'text-left',
                      )}
                    >
                      {canSort ? (
                        <button
                          type="button"
                          onClick={header.column.getToggleSortingHandler()}
                          className={cn(
                            'inline-flex items-center gap-1 rounded hover:text-ink',
                            meta?.align === 'right' && 'flex-row-reverse',
                          )}
                        >
                          {content}
                          {sorted === 'asc' ? (
                            <ArrowUp className="size-3" aria-hidden />
                          ) : sorted === 'desc' ? (
                            <ArrowDown className="size-3" aria-hidden />
                          ) : (
                            <ChevronsUpDown className="size-3 opacity-40" aria-hidden />
                          )}
                        </button>
                      ) : (
                        content
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody ref={body}>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                tabIndex={onOpen ? 0 : undefined}
                onClick={
                  onOpen
                    ? () => {
                        onOpen(row.original);
                      }
                    : undefined
                }
                onKeyDown={(e) => {
                  onRowKey(e, row.original);
                }}
                className={cn(
                  'group bg-surface focus-visible:outline-2 focus-visible:-outline-offset-2',
                  onOpen && 'cursor-pointer hover:bg-canvas',
                  rowClassName?.(row.original),
                )}
              >
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta as ColumnMeta | undefined;
                  return (
                    <td
                      key={cell.id}
                      className={cn(
                        'border-b border-border px-4 align-middle',
                        compact ? 'py-1.5' : 'py-3',
                        meta?.align === 'right' && 'text-right tabular-nums',
                      )}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
