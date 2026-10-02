"use client";

import React, { useState, useEffect } from 'react';
import { Activity, Bot } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { DashboardFeed } from '../../components/DashboardFeed';
import { SystemStatus } from '../../components/SystemStatus';
import { apiUrl } from '../../lib/api';

interface ServiceStatus {
  [key: string]: 'green' | 'yellow' | 'red';
}

export default function DashboardPage() {
  const router = useRouter();
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>({});
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Fetch initial system status
    const fetchStatus = async () => {
      try {
        const response = await fetch(apiUrl('/dashboard/status'));
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

  const handleInvestigate = (event: any) => {
    const query = encodeURIComponent(`Investigate ${event.service} - ${event.message}`);
    window.open(`/?q=${query}`, '_blank');
  };

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-900">
      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Activity className="w-7 h-7 text-blue-600 dark:text-blue-400" />
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                  The Deck
                </h1>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Real-time system health monitoring
                </p>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div className="flex items-center space-x-2 bg-gray-100 dark:bg-gray-900 rounded-lg p-1">
              <button
                onClick={() => router.push('/')}
                className="flex items-center space-x-2 px-4 py-2 rounded-md text-sm font-medium transition-colors text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-gray-800"
              >
                <Bot className="w-4 h-4" />
                <span>Chat</span>
              </button>
              <button
                className="flex items-center space-x-2 px-4 py-2 rounded-md text-sm font-medium transition-colors bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm"
              >
                <Activity className="w-4 h-4" />
                <span>Dashboard</span>
              </button>
            </div>
          </div>
        </header>

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
