"use client";

import React from 'react';
import { AlertCircle, Clock } from 'lucide-react';

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

interface AlertCardProps {
  event: DashboardEvent;
  onClick?: () => void;
}

export function AlertCard({ event, onClick }: AlertCardProps) {
  const severityColors = {
    critical: 'border-red-500 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/30',
    warning: 'border-yellow-500 bg-yellow-50 dark:bg-yellow-900/20 hover:bg-yellow-100 dark:hover:bg-yellow-900/30',
    info: 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 hover:bg-blue-100 dark:hover:bg-blue-900/30',
  };

  const severityIconColors = {
    critical: 'text-red-600 dark:text-red-400',
    warning: 'text-yellow-600 dark:text-yellow-400',
    info: 'text-blue-600 dark:text-blue-400',
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  };

  return (
    <div
      className={`border-l-4 rounded-lg p-4 cursor-pointer transition-all shadow-sm hover:shadow-md ${severityColors[event.severity]}`}
      onClick={onClick}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-start space-x-3 flex-1">
          <AlertCircle className={`w-5 h-5 mt-0.5 flex-shrink-0 ${severityIconColors[event.severity]}`} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center space-x-2 mb-1">
              <h4 className="font-semibold text-gray-900 dark:text-white truncate">
                {event.service}
              </h4>
              {event.error_rate !== undefined && (
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  event.error_rate >= 10
                    ? 'bg-red-200 text-red-800 dark:bg-red-900 dark:text-red-200'
                    : 'bg-yellow-200 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
                }`}>
                  {event.error_rate.toFixed(1)}% errors
                </span>
              )}
            </div>
            <p className="text-sm text-gray-700 dark:text-gray-300 break-words">
              {event.message}
            </p>
            {event.metadata?.diagnosis && (
              <details className="mt-2 text-sm">
                <summary className="cursor-pointer text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200">
                  View diagnosis
                </summary>
                <div className="mt-2 p-2 bg-white dark:bg-gray-800 rounded text-xs text-gray-600 dark:text-gray-400">
                  <pre className="whitespace-pre-wrap">
                    {JSON.stringify(event.metadata.diagnosis, null, 2)}
                  </pre>
                </div>
              </details>
            )}
          </div>
        </div>
        <div className="flex items-center space-x-1 text-gray-500 dark:text-gray-400 flex-shrink-0 ml-2">
          <Clock className="w-4 h-4" />
          <span className="text-xs">{formatTimestamp(event.timestamp)}</span>
        </div>
      </div>
    </div>
  );
}
