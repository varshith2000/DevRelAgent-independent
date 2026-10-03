"use client";

import React from 'react';
import { AppHeader } from '../../components/AppHeader';
import { ApprovalInbox } from '../../components/ApprovalInbox';

export default function ApprovalsPage() {
  return (
    <div className="flex h-screen flex-col bg-gray-50 dark:bg-gray-900">
      <AppHeader active="approvals" title="Approvals" subtitle="Human-in-the-loop review" />
      <main className="flex-1 flex flex-col overflow-hidden">
        <ApprovalInbox className="flex-1 overflow-hidden" />
      </main>
    </div>
  );
}
