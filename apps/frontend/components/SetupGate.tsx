"use client";

import React, { useEffect, useState } from 'react';
import { SetupWizard } from './SetupWizard';

export function SetupGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [complete, setComplete] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const forceSetup = params.get('setup') === '1';
    setComplete(!forceSetup);
    setReady(true);
  }, []);

  if (!ready) {
    return <div className="setup-loading" role="status" aria-label="Loading DevRelAgent"><span /></div>;
  }

  return complete ? <>{children}</> : <SetupWizard onComplete={() => setComplete(true)} />;
}
