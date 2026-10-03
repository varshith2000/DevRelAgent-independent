"use client";

import React from 'react';
import { AppHeader } from '../../components/AppHeader';
import { WorkspaceAdmin } from '../../components/WorkspaceAdmin';

export default function WorkspacePage() {
  return (
    <div className="app-page-frame">
      <AppHeader
        active="workspace"
        title="Workspace"
        subtitle="Projects, members and API keys"
      />
      <main className="flex-1 flex flex-col overflow-hidden">
        <WorkspaceAdmin />
      </main>
    </div>
  );
}
