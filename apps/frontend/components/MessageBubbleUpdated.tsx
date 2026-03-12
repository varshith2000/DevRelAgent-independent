"use client";

import React, { useState } from 'react';
import { Bot, User, Code, FileText, Database, File, Image as ImageIcon, Copy, Check, Shield, TrendingUp, AlertTriangle } from 'lucide-react';

interface UploadedFile {
    name: string;
    type: string;
    size: number;
    content: string;
}

interface Observation {
    observation_id: string;
    observation_type: string;
    title: string;
    description: string;
    impact: string;
    confidence: number;
    suggested_actions: string[];
}

interface Message {
    id: string;
    type: 'user' | 'assistant';
    content: string;
    timestamp: Date;
    sql?: string;
    toolResults?: any[];
    files?: UploadedFile[];
    confidence?: number;
    certaintyLevel?: 'confirmed' | 'likely' | 'possible' | 'uncertain' | 'unknown';
    impact?: 'critical' | 'high' | 'medium' | 'low' | 'informational';
    observations?: Observation[];
    toolExplanation?: any;
    requiresApproval?: boolean;
}

interface MessageBubbleProps {
    message: Message;
}

// Confidence level colors
const getConfidenceColor = (confidence?: number, certaintyLevel?: string) => {
    if (!confidence) return 'text-gray-500';

    if (confidence >= 0.9 || certaintyLevel === 'confirmed') {
        return 'text-green-600';
    } else if (confidence >= 0.7 || certaintyLevel === 'likely') {
        return 'text-blue-600';
    } else if (confidence >= 0.5 || certaintyLevel === 'possible') {
        return 'text-yellow-600';
    } else {
        return 'text-orange-600';
    }
};

// Impact level colors and icons
const getImpactInfo = (impact?: string) => {
    const impactMap = {
        critical: { color: 'text-red-600 bg-red-50', icon: AlertTriangle, label: 'Critical' },
        high: { color: 'text-orange-600 bg-orange-50', icon: TrendingUp, label: 'High' },
        medium: { color: 'text-yellow-600 bg-yellow-50', icon: Shield, label: 'Medium' },
        low: { color: 'text-blue-600 bg-blue-50', icon: Shield, label: 'Low' },
        informational: { color: 'text-gray-600 bg-gray-50', icon: FileText, label: 'Info' },
    };

    return impactMap[impact as keyof typeof impactMap] || impactMap.informational;
};

export function MessageBubble({ message }: MessageBubbleProps) {
    const isUser = message.type === 'user';
    const [copiedCode, setCopiedCode] = useState<string | null>(null);
    const [showObservations, setShowObservations] = useState(false);

    const copyToClipboard = (code: string, id: string) => {
        navigator.clipboard.writeText(code);
        setCopiedCode(id);
        setTimeout(() => setCopiedCode(null), 2000);
    };

    const formatContent = (content: string) => {
        // Split by code blocks first
        const codeBlockRegex = /```(\w*)\n([\s\S]*?)```/g;
        const parts = [];
        let lastIndex = 0;
        let match;

        while ((match = codeBlockRegex.exec(content)) !== null) {
            // Add text before code block
            if (match.index > lastIndex) {
                parts.push({
                    type: 'text',
                    content: content.slice(lastIndex, match.index)
                });
            }

            // Add code block
            parts.push({
                type: 'code',
                language: match[1] || 'text',
                content: match[2]
            });

            lastIndex = match.index + match[0].length;
        }

        // Add remaining text
        if (lastIndex < content.length) {
            parts.push({
                type: 'text',
                content: content.slice(lastIndex)
            });
        }

        // If no code blocks found, treat entire content as text
        if (parts.length === 0) {
            parts.push({ type: 'text', content });
        }

        return parts.map((part, index) => {
            if (part.type === 'code') {
                const codeId = `code-${message.id}-${index}`;
                return (
                    <div key={index} className="my-3">
                        <div className="relative group">
                            {/* Copy button */}
                            <button
                                onClick={() => copyToClipboard(part.content, codeId)}
                                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-gray-700 hover:bg-gray-600 text-white px-2 py-1 rounded text-xs flex items-center space-x-1 z-10"
                            >
                                {copiedCode === codeId ? (
                                    <>
                                        <Check className="w-3 h-3" />
                                        <span>Copied!</span>
                                    </>
                                ) : (
                                    <>
                                        <Copy className="w-3 h-3" />
                                        <span>Copy</span>
                                    </>
                                )}
                            </button>

                            {/* Code block */}
                            <div className="bg-gray-900 dark:bg-gray-950 rounded-lg overflow-hidden border border-gray-700">
                                {/* Language header */}
                                {part.language && part.language !== 'text' && (
                                    <div className="bg-gray-800 dark:bg-gray-900 px-4 py-2 border-b border-gray-700">
                                        <div className="flex items-center text-xs text-gray-400">
                                            <Code className="w-3 h-3 mr-2" />
                                            <span className="uppercase font-mono">{part.language}</span>
                                        </div>
                                    </div>
                                )}

                                {/* Code content */}
                                <div className="p-4 overflow-x-auto">
                                    <pre className="text-sm font-mono">
                                        <code className="text-gray-100 dark:text-gray-100 whitespace-pre">
                                            {part.content}
                                        </code>
                                    </pre>
                                </div>
                            </div>
                        </div>
                    </div>
                );
            } else {
                // Format text with inline code support
                return (
                    <span key={index} className="whitespace-pre-wrap">
                        {formatInlineCode(part.content)}
                    </span>
                );
            }
        });
    };

    const formatInlineCode = (text: string) => {
        // Split by inline code (single backticks)
        const inlineCodeRegex = /`([^`]+)`/g;
        const parts = [];
        let lastIndex = 0;
        let match;

        while ((match = inlineCodeRegex.exec(text)) !== null) {
            // Add text before inline code
            if (match.index > lastIndex) {
                parts.push({
                    type: 'text',
                    content: text.slice(lastIndex, match.index)
                });
            }

            // Add inline code
            parts.push({
                type: 'inline',
                content: match[1]
            });

            lastIndex = match.index + match[0].length;
        }

        // Add remaining text
        if (lastIndex < text.length) {
            parts.push({
                type: 'text',
                content: text.slice(lastIndex)
            });
        }

        // If no inline code found, return original text
        if (parts.length === 0) {
            return text;
        }

        return parts.map((part, index) => {
            if (part.type === 'inline') {
                return (
                    <code
                        key={index}
                        className="bg-gray-200 dark:bg-gray-700 text-red-600 dark:text-red-400 px-1.5 py-0.5 rounded text-sm font-mono mx-1"
                    >
                        {part.content}
                    </code>
                );
            }
            return <span key={index}>{part.content}</span>;
        });
    };

    const impactInfo = getImpactInfo(message.impact);
    const ImpactIcon = impactInfo.icon;
    const confidenceColor = getConfidenceColor(message.confidence, message.certaintyLevel);

    return (
        <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div className={`flex max-w-[80%] ${isUser ? 'flex-row-reverse' : 'flex-row'} items-start space-x-2`}>
                {/* Avatar */}
                <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${isUser
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                    }`}>
                    {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                </div>

                {/* Message Content */}
                <div className={`rounded-lg px-4 py-2 ${isUser
                        ? 'bg-blue-600 text-white'
                        : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white'
                    }`}>
                    <div className="text-sm">
                        {formatContent(message.content)}
                    </div>

                    {/* Confidence & Impact Indicators (Assistant only) */}
                    {!isUser && (message.confidence !== undefined || message.impact) && (
                        <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                            <div className="flex items-center justify-between flex-wrap gap-2">
                                {/* Confidence Badge */}
                                {message.confidence !== undefined && (
                                    <div className={`flex items-center space-x-1 text-xs ${confidenceColor}`}>
                                        <Shield className="w-3 h-3" />
                                        <span>
                                            {message.certaintyLevel || 'possible'} ({Math.round((message.confidence || 0) * 100)}%)
                                        </span>
                                    </div>
                                )}

                                {/* Impact Badge */}
                                {message.impact && (
                                    <div className={`flex items-center space-x-1 text-xs px-2 py-1 rounded ${impactInfo.color}`}>
                                        <ImpactIcon className="w-3 h-3" />
                                        <span>{impactInfo.label}</span>
                                    </div>
                                )}
                            </div>

                            {/* Observations Toggle */}
                            {message.observations && message.observations.length > 0 && (
                                <div className="mt-2">
                                    <button
                                        onClick={() => setShowObservations(!showObservations)}
                                        className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                                    >
                                        {showObservations ? 'Hide' : 'Show'} Observations ({message.observations.length})
                                    </button>

                                    {showObservations && (
                                        <div className="mt-2 space-y-2">
                                            {message.observations.map((obs, idx) => (
                                                <div key={idx} className="bg-gray-50 dark:bg-gray-900 rounded p-2 text-xs">
                                                    <div className="font-medium text-gray-900 dark:text-white">
                                                        {obs.title}
                                                    </div>
                                                    <div className="text-gray-600 dark:text-gray-400 mt-1">
                                                        {obs.description}
                                                    </div>
                                                    {obs.suggested_actions && obs.suggested_actions.length > 0 && (
                                                        <div className="mt-2">
                                                            <div className="font-medium text-gray-700 dark:text-gray-300">
                                                                Suggested Actions:
                                                            </div>
                                                            <ul className="list-disc list-inside text-gray-600 dark:text-gray-400 ml-2">
                                                                {obs.suggested_actions.map((action, i) => (
                                                                    <li key={i}>{action}</li>
                                                                ))}
                                                            </ul>
                                                        </div>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Tool Explanation */}
                    {message.toolExplanation && (
                        <div className="mt-3 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                            <div className="flex items-center space-x-2 mb-2">
                                <Shield className="w-4 h-4 text-blue-600" />
                                <span className="text-xs font-medium text-blue-900 dark:text-blue-100">
                                    Before Executing:
                                </span>
                            </div>
                            <div className="text-xs text-gray-700 dark:text-gray-300 space-y-1">
                                <div><strong>Action:</strong> {message.toolExplanation.action}</div>
                                <div><strong>Reasoning:</strong> {message.toolExplanation.reasoning}</div>
                                <div><strong>Expected Outcome:</strong> {message.toolExplanation.expected_outcome}</div>
                                {message.toolExplanation.risk_level && (
                                    <div><strong>Risk Level:</strong> <span className="uppercase">{message.toolExplanation.risk_level}</span></div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Tool Results */}
                    {message.toolResults && message.toolResults.length > 0 && (
                        <div className="mt-3 space-y-2">
                            {message.toolResults.map((result, index) => (
                                <div key={index} className="bg-white dark:bg-gray-900 rounded p-2 text-xs">
                                    <div className="flex items-center text-gray-500 dark:text-gray-400 mb-1">
                                        <Database className="w-3 h-3 mr-1" />
                                        Tool: {result.tool_name || 'Unknown'}
                                    </div>
                                    <pre className="whitespace-pre-wrap text-gray-700 dark:text-gray-300">
                                        {JSON.stringify(result.result, null, 2)}
                                    </pre>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* File Attachments */}
                    {message.files && message.files.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-2">
                            {message.files.map((file, idx) => {
                                const ext = file.name.split('.').pop()?.toLowerCase() || '';
                                const isImage = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg', 'webp'].includes(ext);
                                const Icon = isImage ? ImageIcon : (file.name.endsWith('.pdf') || file.name.endsWith('.docx') ? FileText : File);

                                return (
                                    <div
                                        key={idx}
                                        className={`flex items-center space-x-2 rounded-lg px-3 py-2 text-sm ${
                                            isUser
                                                ? 'bg-blue-500/20 text-blue-100'
                                                : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                                        }`}
                                    >
                                        <Icon className="w-4 h-4" />
                                        <span className="max-w-[200px] truncate">{file.name}</span>
                                        <span className={`text-xs ${isUser ? 'text-blue-200' : 'text-gray-500 dark:text-gray-400'}`}>
                                            {(file.size / 1024).toFixed(1)} KB
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    )}

                    {/* Timestamp */}
                    <div className={`text-xs mt-1 ${isUser ? 'text-blue-100' : 'text-gray-500 dark:text-gray-400'
                        }`}>
                        {message.timestamp.toLocaleTimeString()}
                    </div>
                </div>
            </div>
        </div>
    );
}
