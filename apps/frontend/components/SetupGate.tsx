"use client";

import React, { useEffect, useState } from 'react';
import { SetupWizard } from './SetupWizard';
import { hasCompletedSetup } from '../lib/setup';

export function SetupGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [complete, setComplete] = useState(false);

  useEffect(() => {
    setComplete(hasCompletedSetup());
    setReady(true);
  }, []);

  if (!ready) {
    return <div className="setup-loading" role="status" aria-label="Loading DevRelAgent"><span /></div>;
  }

  return complete ? <>{children}</> : <SetupWizard onComplete={() => setComplete(true)} />;
}
