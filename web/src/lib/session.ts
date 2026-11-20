/**
 * The desk session. In demo mode the API signs every request in as the demo desk user; the client
 * only remembers that the person chose to enter the demo workspace. Storage can be unavailable
 * (private windows), so access is guarded.
 */
import { useSyncExternalStore } from 'react';

const KEY = 'arzi.session';
const listeners = new Set<() => void>();

function read(): boolean {
  try {
    return window.localStorage.getItem(KEY) === 'demo';
  } catch {
    return memory;
  }
}

let memory = false;

function write(value: boolean): void {
  memory = value;
  try {
    if (value) window.localStorage.setItem(KEY, 'demo');
    else window.localStorage.removeItem(KEY);
  } catch {
    // Storage blocked: keep the session in memory for this tab.
  }
  listeners.forEach((l) => {
    l();
  });
}

export function signIn(): void {
  write(true);
}

export function signOut(): void {
  write(false);
}

export function useSignedIn(): boolean {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    read,
    () => false,
  );
}

/** A remembered UI preference (sidebar collapsed, table density). Never business data. */
export function preference(key: string, fallback: boolean): boolean {
  try {
    const value = window.localStorage.getItem(`arzi.pref.${key}`);
    return value === null ? fallback : value === '1';
  } catch {
    return fallback;
  }
}

export function setPreference(key: string, value: boolean): void {
  try {
    window.localStorage.setItem(`arzi.pref.${key}`, value ? '1' : '0');
  } catch {
    // Not persisted; the choice still applies for this page view.
  }
}
