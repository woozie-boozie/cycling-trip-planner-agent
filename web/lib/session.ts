/**
 * Session id management — survives page refresh via localStorage.
 *
 * The backend treats session_id as opaque. We generate a fresh one only
 * when the user explicitly resets, or when no key is present yet.
 */

const STORAGE_KEY = "ctp:session_id";

export function loadSessionId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function saveSessionId(id: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // localStorage unavailable (private mode, quota, etc.) — fail silently;
    // session just resets per page load.
  }
}

export function clearSessionId(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // see above
  }
}
