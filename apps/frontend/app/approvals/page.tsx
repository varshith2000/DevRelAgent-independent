"use client";

import React from 'react';
import { AppHeader } from '../../components/AppHeader';
import { ApprovalInbox } from '../../components/ApprovalInbox';

export default function ApprovalsPage() {
  return (
    <div className="app-page-frame">
      <AppHeader active="approvals" title="Approvals" subtitle="Human-in-the-loop review" />
      <main className="flex-1 flex flex-col overflow-hidden">
        <ApprovalInbox className="flex-1 overflow-hidden" />
      </main>
    </div>
  );
}
