"use client";

import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Brain, Loader2 } from 'lucide-react';

interface ReasoningStepProps {
  stepNumber: number;
  thought: string;
  action: string;
  observation?: string;
  toolsUsed?: string[];
  timestamp?: string;
}

interface ReasoningStepsProps {
  steps: ReasoningStepProps[];
  className?: string;
}

export function ReasoningSteps({ steps, className = '' }: ReasoningStepsProps) {
  const [expanded, setExpanded] = useState(true);
  const [loadingStep, setLoadingStep] = useState<number | null>(null);

  const formatAction = (action: string) => {
    if (action.startsWith('COMPLETE:')) {
      return {
        type: 'complete',
        content: action.replace('COMPLETE:', '').trim(),
        icon: '✓'
      };
    }
    if (action.startsWith('USE_TOOL:')) {
      return {
        type: 'tool',
        content: action.replace('USE_TOOL:', '').trim(),
        icon: '⚙'
      };
    }
    return {
      type: 'unknown',
      content: action,
      icon: '→'
    };
  };

  if (steps.length === 0) {
    return null;
  }

  return (
    <div className={`bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg ${className}`}>
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-6 py-4 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors rounded-t-lg"
      >
        <div className="flex items-center space-x-3">
          <Brain className="w-5 h-5 text-purple-600 dark:text-purple-400" />
          <span className="font-semibold text-gray-900 dark:text-white">Reasoning Process</span>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            ({steps.length} steps)
          </span>
        </div>
        {expanded ? (
          <ChevronUp className="w-5 h-5 text-gray-500 dark:text-gray-400" />
        ) : (
          <ChevronDown className="w-5 h-5 text-gray-500 dark:text-gray-400" />
        )}
      </button>

      {/* Steps */}
      {expanded && (
        <div className="px-6 pb-4 space-y-4">
          {steps.map((step, index) => {
            const action = formatAction(step.action);

            return (
              <div
                key={step.stepNumber}
                className="border-l-2 border-purple-500 pl-4 space-y-2"
              >
                {/* Step Header */}
                <div className="flex items-center space-x-2">
                  <span className="flex-shrink-0 w-6 h-6 flex items-center justify-center bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 rounded-full text-sm font-semibold">
                    {step.stepNumber}
                  </span>
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Step {step.stepNumber}
                  </span>
                  {step.toolsUsed && step.toolsUsed.length > 0 && (
                    <span className="text-xs px-2 py-0.5 bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 rounded-full">
                      {step.toolsUsed.join(', ')}
                    </span>
                  )}
                </div>

                {/* Thought */}
                <div className="ml-8">
                  <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
                    Thought
                  </div>
                  <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                    {step.thought}
                  </p>
                </div>

                {/* Action */}
                <div className="ml-8">
                  <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
                    Action
                  </div>
                  <div className={`flex items-start space-x-2 ${
                    action.type === 'complete'
                      ? 'text-green-700 dark:text-green-300'
                      : 'text-blue-700 dark:text-blue-300'
                  }`}>
                    <span className="flex-shrink-0">{action.icon}</span>
                    <p className="text-sm font-mono flex-1">
                      {action.content}
                    </p>
                  </div>
                </div>

                {/* Observation */}
                {step.observation && (
                  <div className="ml-8">
                    <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
                      Observation
                    </div>
                    <div className="bg-white dark:bg-gray-900 rounded border border-gray-200 dark:border-gray-700 p-3">
                      <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap font-mono">
                        {step.observation}
                      </p>
                    </div>
                  </div>
                )}

                {/* Timestamp */}
                {step.timestamp && (
                  <div className="ml-8 text-xs text-gray-400 dark:text-gray-500">
                    {new Date(step.timestamp).toLocaleTimeString()}
                  </div>
                )}
              </div>
            );
          })}

          {/* Summary */}
          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
            <div className="text-sm text-gray-600 dark:text-gray-400">
              <span className="font-medium">Summary:</span> Multi-step reasoning completed with {steps.length} steps to analyze the query.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Loading state for reasoning
export function ReasoningStepsLoading({ className = '' }: { className?: string }) {
  return (
    <div className={`bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-6 ${className}`}>
      <div className="flex items-center space-x-3">
        <Loader2 className="w-5 h-5 text-purple-600 dark:text-purple-400 animate-spin" />
        <span className="font-semibold text-gray-900 dark:text-white">Analyzing with multi-step reasoning...</span>
      </div>
      <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
        Breaking down the query into steps and gathering information from multiple sources...
      </p>
    </div>
  );
}
