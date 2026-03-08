"use client";

import React from 'react';
import { AlertTriangle, Info, AlertCircle, XCircle } from 'lucide-react';

interface ApprovalCardProps {
  approvalId: string;
  actionType: string;
  plan: string[];
  riskLevel: 'low' | 'medium' | 'high' | 'critical';
  metadata?: Record<string, any>;
  onApprove: () => void;
  onReject: () => void;
  isLoading?: boolean;
  className?: string;
}

export function ApprovalCard({
  approvalId,
  actionType,
  plan,
  riskLevel,
  metadata = {},
  onApprove,
  onReject,
  isLoading = false,
  className = ''
}: ApprovalCardProps) {
  const riskConfig = {
    low: {
      border: 'border-green-500',
      bg: 'bg-green-50 dark:bg-green-900/20',
      badge: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
      icon: Info,
      iconColor: 'text-green-600 dark:text-green-400'
    },
    medium: {
      border: 'border-yellow-500',
      bg: 'bg-yellow-50 dark:bg-yellow-900/20',
      badge: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
      icon: AlertTriangle,
      iconColor: 'text-yellow-600 dark:text-yellow-400'
    },
    high: {
      border: 'border-orange-500',
      bg: 'bg-orange-50 dark:bg-orange-900/20',
      badge: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
      icon: AlertTriangle,
      iconColor: 'text-orange-600 dark:text-orange-400'
    },
    critical: {
      border: 'border-red-500',
      bg: 'bg-red-50 dark:bg-red-900/20',
      badge: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
      icon: XCircle,
      iconColor: 'text-red-600 dark:text-red-400'
    }
  };

  const config = riskConfig[riskLevel];
  const Icon = config.icon;

  const formatActionType = (type: string) => {
    return type
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  return (
    <div className={`border-l-4 ${config.border} ${config.bg} rounded-lg p-6 shadow-lg ${className}`}>
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center space-x-3">
          <Icon className={`w-6 h-6 ${config.iconColor} flex-shrink-0`} />
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Approval Required
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-0.5">
              Action: {formatActionType(actionType)}
            </p>
          </div>
        </div>
        <span className={`px-3 py-1 rounded-full text-xs font-semibold ${config.badge}`}>
          {riskLevel.toUpperCase()} RISK
        </span>
      </div>

      {/* Plan */}
      <div className="mb-6">
        <h4 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
          Execution Plan:
        </h4>
        <ol className="space-y-2">
          {plan.map((step, index) => (
            <li key={index} className="flex items-start space-x-3">
              <span className="flex-shrink-0 w-6 h-6 flex items-center justify-center bg-white dark:bg-gray-800 rounded-full text-sm font-medium text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-600">
                {index + 1}
              </span>
              <span className="text-sm text-gray-700 dark:text-gray-300 flex-1 pt-0.5">
                {step}
              </span>
            </li>
          ))}
        </ol>
      </div>

      {/* Metadata */}
      {Object.keys(metadata).length > 0 && (
        <details className="mb-6">
          <summary className="cursor-pointer text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white">
            View Details
          </summary>
          <div className="mt-3 p-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
            <pre className="text-xs text-gray-600 dark:text-gray-400 overflow-x-auto">
              {JSON.stringify(metadata, null, 2)}
            </pre>
          </div>
        </details>
      )}

      {/* Warning Message */}
      {riskLevel === 'critical' && (
        <div className="mb-6 p-3 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-700 rounded-lg">
          <p className="text-sm text-red-800 dark:text-red-200">
            <strong>Warning:</strong> This action is marked as critical and could have significant impact.
            Please review carefully before approving.
          </p>
        </div>
      )}

      {/* Actions */}
      <div className="flex space-x-3">
        <button
          onClick={onApprove}
          disabled={isLoading}
          className="flex-1 flex items-center justify-center space-x-2 bg-green-600 hover:bg-green-700 disabled:bg-green-400 text-white px-4 py-3 rounded-lg font-medium transition-colors disabled:cursor-not-allowed"
        >
          {isLoading ? (
            <>
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
              <span>Processing...</span>
            </>
          ) : (
            <>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <span>Approve</span>
            </>
          )}
        </button>
        <button
          onClick={onReject}
          disabled={isLoading}
          className="flex-1 flex items-center justify-center space-x-2 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white px-4 py-3 rounded-lg font-medium transition-colors disabled:cursor-not-allowed"
        >
          <XCircle className="w-5 h-5" />
          <span>Reject</span>
        </button>
      </div>

      {/* Approval ID */}
      <p className="mt-4 text-xs text-gray-500 dark:text-gray-400 text-center">
        Approval ID: {approvalId}
      </p>
    </div>
  );
}
