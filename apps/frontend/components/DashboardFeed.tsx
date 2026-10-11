"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { AlertCard } from './AlertCard';
import { apiFetch } from '../lib/api';
import { withBasePath } from '../lib/app-config';
import { openStream, type StreamHandle } from '../lib/stream';
import { IDENTITY_EVENT } from '../lib/auth';

interface DashboardEvent {
  id: string;
  type: 'alert' | 'health_check' | 'error_spike';
  severity: 'critical' | 'warning' | 'info';
  service: string;
  message: string;
  error_rate?: number;
  timestamp: string;
  metadata?: Record<string, any>;
}

interface DashboardFeedProps {
  onInvestigate?: (event: DashboardEvent) => void;
  className?: string;
}

export function DashboardFeed({ onInvestigate, className = '' }: DashboardFeedProps) {
  const [events, setEvents] = useState<DashboardEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Bumped whenever the identity or active project changes, to reconnect.
  const [scope, setScope] = useState(0);

  useEffect(() => {
    const onIdentityChange = () => setScope((n) => n + 1);
    window.addEventListener(IDENTITY_EVENT, onIdentityChange);
    return () => window.removeEventListener(IDENTITY_EVENT, onIdentityChange);
  }, []);

  useEffect(() => {
    let stream: StreamHandle | null = null;
    let reconnectTimer: NodeJS.Timeout | null = null;

    const connect = () => {
      try {
        stream = openStream('/dashboard/stream', {
          onOpen: () => {
            setIsConnected(true);
            setError(null);
          },
          onError: () => {
            setIsConnected(false);
            setError('Live activity disconnected. Retrying shortly.');

            // Reconnect after 5 seconds
            if (reconnectTimer) clearTimeout(reconnectTimer);
            reconnectTimer = setTimeout(() => {
              stream?.close();
              connect();
            }, 5000);
          },
          onMessage: (raw) => {
            try {
              const data = JSON.parse(raw);

              if (data.type === 'connected') {
                // Stream is live; the header indicator reflects the current connection state.
              } else if (data.type === 'ping') {
                // Keepalive, ignore
              } else if (data.type === 'system_status') {
                // System status update, could be used to update status component
              } else if (data.type === 'alert' && data.data) {
                // New alert
                setEvents(prev => [data.data, ...prev].slice(0, 100)); // Keep last 100
              } else if (data.type === 'error') {
                setError(data.error || 'Stream error');
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', e);
            }
          },
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to connect to dashboard');
      }
    };

    connect();

    // Initial fetch of recent alerts
    apiFetch('/dashboard/alerts?limit=20')
      .then((res) => {
        if (!res.ok) throw new Error(`Alert history request failed (${res.status}).`);
        return res.json();
      })
      .then(async (data) => {
        if (data.alerts) {
          setEvents(data.alerts);
        }
      })
      .catch(e => {
        console.error('Failed to fetch initial alerts:', e);
        setError(e instanceof Error ? e.message : 'Failed to load recent activity.');
      });

    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      stream?.close();
    };
  }, [scope]);

  const handleRefresh = useCallback(async () => {
    try {
      const response = await apiFetch('/dashboard/alerts?limit=20');
      if (!response.ok) throw new Error(`Refresh failed (${response.status}).`);
      const data = await response.json();
      if (data.alerts) {
        setEvents(data.alerts);
      }
    } catch (e) {
      console.error('Failed to refresh alerts:', e);
    }
  }, []);

  const handleInvestigate = useCallback((event: DashboardEvent) => {
    if (onInvestigate) {
      onInvestigate(event);
    } else {
      // Default behavior: navigate to chat with investigation query
      const query = new URLSearchParams({ q: `Investigate ${event.service} - ${event.message}` });
      window.location.assign(withBasePath(`/?${query.toString()}`));
    }
  }, [onInvestigate]);

  return (
    <div className={`dashboard-feed flex flex-col ${className}`}>
      {/* Header */}
      <div className="dashboard-feed-header flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <div className="flex items-center space-x-2">
          <AlertCircle className="w-5 h-5 text-gray-600 dark:text-gray-400" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Activity Feed
          </h2>
        </div>
        <div className="flex items-center space-x-3">
          <div role="status" aria-live="polite" className={`dashboard-stream-status flex items-center space-x-2 text-sm ${
            isConnected ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
          }`}>
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></div>
            <span>{isConnected ? 'Live' : 'Disconnected'}</span>
          </div>
          <button
            onClick={handleRefresh}
            className="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="dashboard-feed-error mx-6 mt-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-500 rounded-lg" role="alert">
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      {/* Events */}
      <div className="dashboard-feed-events flex-1 overflow-y-auto px-6 py-4 space-y-3 bg-gray-50 dark:bg-gray-900">
        {events.length === 0 ? (
          <div className="dashboard-empty-state text-center py-12">
            <AlertCircle className="w-12 h-12 mx-auto text-gray-400 dark:text-gray-600 mb-4" />
            <p className="text-gray-500 dark:text-gray-400">No alerts yet</p>
            <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">
              {isConnected ? 'Live monitoring is connected. New alerts will appear here.' : 'Connect the backend and monitoring integrations to receive live alerts.'}
            </p>
          </div>
        ) : (
          events.map(event => (
            <AlertCard
              key={event.id}
              event={event}
              onClick={() => handleInvestigate(event)}
            />
          ))
        )}
      </div>
    </div>
  );
}
