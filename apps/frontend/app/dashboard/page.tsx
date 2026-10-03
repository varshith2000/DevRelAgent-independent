"use client";

import React, { useState, useEffect } from 'react';
import { AppHeader } from '../../components/AppHeader';
import { DashboardFeed } from '../../components/DashboardFeed';
import { SystemStatus } from '../../components/SystemStatus';
import { apiFetch } from '../../lib/api';

interface ServiceStatus {
  [key: string]: 'green' | 'yellow' | 'red';
}

export default function DashboardPage() {
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>({});
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Fetch initial system status
    const fetchStatus = async () => {
      try {
        const response = await apiFetch('/dashboard/status');
        if (!response.ok) throw new Error(`Dashboard status request failed (${response.status}).`);
        const data = await response.json();
        if (data.services) {
          setServiceStatus(data.services);
        }
      } catch (error) {
        console.error('Failed to fetch system status:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchStatus();

    // Refresh status every 30 seconds
    const interval = setInterval(fetchStatus, 30000);

    return () => clearInterval(interval);
  }, []);

  const handleInvestigate = (event: { service: string; message: string }) => {
    const query = new URLSearchParams({ q: `Investigate ${event.service} - ${event.message}` });
    window.location.assign(`/?${query.toString()}`);
  };

  return (
    <div className="app-page-frame">
      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <AppHeader
          active="dashboard"
          title="The Deck"
          subtitle="Real-time system health monitoring"
        />

        {/* System Status */}
        {!isLoading && (
          <SystemStatus services={serviceStatus} />
        )}

        {/* Dashboard Feed */}
        <DashboardFeed
          onInvestigate={handleInvestigate}
          className="flex-1 overflow-hidden"
        />
      </main>
    </div>
  );
}
