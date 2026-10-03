const SETUP_COMPLETE_KEY = 'devrelagent.setup-complete';

export function hasCompletedSetup(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(SETUP_COMPLETE_KEY) === 'true';
  } catch {
    return false;
  }
}

export function setSetupComplete(complete: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    if (complete) window.localStorage.setItem(SETUP_COMPLETE_KEY, 'true');
    else window.localStorage.removeItem(SETUP_COMPLETE_KEY);
  } catch {
    // The onboarding should remain usable if browser storage is unavailable.
  }
}
