"use client";

import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Database, Copy, Check } from 'lucide-react';

interface SqlSandboxProps {
    sql: string;
    className?: string;
}

export function SqlSandbox({ sql, className = '' }: SqlSandboxProps) {
    const [isExpanded, setIsExpanded] = useState(false);
    const [copied, setCopied] = useState(false);

    if (!sql) return null;

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(sql);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch (err) {
            console.error('Failed to copy SQL:', err);
        }
    };

    return (
        <div className={`border-t border-gray-200 dark:border-gray-700 ${className}`}>
            {/* Header */}
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full flex items-center justify-between p-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
                <div className="flex items-center space-x-2 text-sm text-gray-600 dark:text-gray-400">
                    <Database className="w-4 h-4" />
                    <span>SQL Query Executed</span>
                </div>
                {isExpanded ? (
                    <ChevronUp className="w-4 h-4 text-gray-400" />
                ) : (
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                )}
            </button>

            {/* SQL Content */}
            {isExpanded && (
                <div className="px-3 pb-3">
                    <div className="relative bg-gray-100 dark:bg-gray-800 rounded-lg p-3">
                        {/* Copy Button */}
                        <button
                            onClick={handleCopy}
                            className="absolute top-2 right-2 p-1 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors"
                            title="Copy SQL"
                        >
                            {copied ? (
                                <Check className="w-4 h-4 text-green-500" />
                            ) : (
                                <Copy className="w-4 h-4" />
                            )}
                        </button>

                        {/* SQL Code */}
                        <pre className="text-sm font-mono text-gray-800 dark:text-gray-200 whitespace-pre-wrap pr-8 overflow-x-auto">
                            {sql}
                        </pre>
                    </div>
                </div>
            )}
        </div>
    );
}