"use client";

import React from 'react';
import { CheckCircle, AlertTriangle, XCircle } from 'lucide-react';

interface ServiceStatus {
  name: string;
  status: 'green' | 'yellow' | 'red';
  lastCheck?: string;
}

interface SystemStatusProps {
  services: Record<string, 'green' | 'yellow' | 'red'>;
  className?: string;
}

export function SystemStatus({ services, className = '' }: SystemStatusProps) {
  const statusConfig = {
    green: {
      bg: 'bg-green-100 dark:bg-green-900/20',
      border: 'border-green-500',
      text: 'text-green-700 dark:text-green-300',
      icon: CheckCircle,
      iconColor: 'text-green-600 dark:text-green-400',
      label: 'Healthy'
    },
    yellow: {
      bg: 'bg-yellow-100 dark:bg-yellow-900/20',
      border: 'border-yellow-500',
      text: 'text-yellow-700 dark:text-yellow-300',
      icon: AlertTriangle,
      iconColor: 'text-yellow-600 dark:text-yellow-400',
      label: 'Warning'
    },
    red: {
      bg: 'bg-red-100 dark:bg-red-900/20',
      border: 'border-red-500',
      text: 'text-red-700 dark:text-red-300',
      icon: XCircle,
      iconColor: 'text-red-600 dark:text-red-400',
      label: 'Critical'
    }
  };

  const serviceList: ServiceStatus[] = Object.entries(services).map(([name, status]) => ({
    name,
    status,
    lastCheck: new Date().toISOString()
  }));

  const statusCounts = {
    green: serviceList.filter(s => s.status === 'green').length,
    yellow: serviceList.filter(s => s.status === 'yellow').length,
    red: serviceList.filter(s => s.status === 'red').length,
  };

  return (
    <div className={`bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 ${className}`}>
      <div className="max-w-7xl mx-auto px-6 py-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">System Status</h2>
          <div className="flex items-center space-x-4 text-sm">
            <div className="flex items-center space-x-1">
              <div className="w-2 h-2 bg-green-500 rounded-full"></div>
              <span className="text-gray-600 dark:text-gray-400">{statusCounts.green} Healthy</span>
            </div>
            <div className="flex items-center space-x-1">
              <div className="w-2 h-2 bg-yellow-500 rounded-full"></div>
              <span className="text-gray-600 dark:text-gray-400">{statusCounts.yellow} Warning</span>
            </div>
            <div className="flex items-center space-x-1">
              <div className="w-2 h-2 bg-red-500 rounded-full"></div>
              <span className="text-gray-600 dark:text-gray-400">{statusCounts.red} Critical</span>
            </div>
          </div>
        </div>

        {serviceList.length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {serviceList.map((service) => {
              const config = statusConfig[service.status];
              const Icon = config.icon;

              return (
                <div
                  key={service.name}
                  className={`${config.bg} ${config.border} border rounded-lg p-3 transition-all hover:shadow-md`}
                >
                  <div className="flex items-center space-x-2">
                    <Icon className={`w-4 h-4 ${config.iconColor} flex-shrink-0`} />
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium ${config.text} truncate`}>
                        {service.name}
                      </p>
                      <p className={`text-xs ${config.text} opacity-75`}>
                        {config.label}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <p>No services currently monitored</p>
          </div>
        )}
      </div>
    </div>
  );
}
