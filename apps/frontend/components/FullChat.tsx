"use client";

import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Paperclip, X, Plus, Clock, Trash2, FileText, Image, File, Activity, LayoutDashboard } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { MessageBubble } from './MessageBubble';
import { SqlSandbox } from './SqlSandbox';
import { DashboardFeed } from './DashboardFeed';
import { apiFetch } from '../lib/api';

interface Message {
    id: string;
    type: 'user' | 'assistant';
    content: string;
    timestamp: Date;
    sql?: string;
    toolResults?: any[];
    files?: UploadedFile[];
}

interface UploadedFile {
    name: string;
    type: string;
    size: number;
    content: string;
}

interface Conversation {
    id: string;
    title: string;
    messages: Message[];
    timestamp: Date;
}

export function FullChat() {
    const router = useRouter();
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
    const [inputValue, setInputValue] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isTyping, setIsTyping] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const [currentView, setCurrentView] = useState<'chat' | 'dashboard'>('chat');

    // Load conversations from localStorage on mount
    useEffect(() => {
        const saved = localStorage.getItem('devrel-conversations');
        if (saved) {
            const parsed = JSON.parse(saved);
            const convs: Conversation[] = parsed.map((c: any) => ({
                ...c,
                messages: c.messages.map((m: any) => ({
                    ...m,
                    timestamp: new Date(m.timestamp)
                })),
                timestamp: new Date(c.timestamp)
            }));
            setConversations(convs);
            if (convs.length > 0) {
                setCurrentConversationId(convs[0].id);
            }
        } else {
            // Create initial conversation
            createNewConversation();
        }
    }, []);

    // Save conversations to localStorage whenever they change
    useEffect(() => {
        if (conversations.length > 0) {
            localStorage.setItem('devrel-conversations', JSON.stringify(conversations));
        }
    }, [conversations]);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [currentConversationId, conversations]);

    const createNewConversation = () => {
        const newConv: Conversation = {
            id: Date.now().toString(),
            title: 'New Conversation',
            messages: [
                {
                    id: '1',
                    type: 'assistant',
                    content: "Hi! I'm your DevRel Agent. I can help you with:\n\n• 📚 Documentation search\n• 📊 Log analysis\n• 🐛 Issue diagnosis\n• 📝 Code review\n• 📄 File analysis (PDF, Word, text, images)\n\nYou can upload files by clicking the attachment button, or just ask me anything!",
                    timestamp: new Date(),
                }
            ],
            timestamp: new Date(),
        };
        setConversations(prev => [newConv, ...prev]);
        setCurrentConversationId(newConv.id);
        setUploadedFiles([]);
    };

    const deleteConversation = (id: string) => {
        setConversations(prev => prev.filter(c => c.id !== id));
        if (currentConversationId === id) {
            const remaining = conversations.filter(c => c.id !== id);
            if (remaining.length > 0) {
                setCurrentConversationId(remaining[0].id);
            } else {
                createNewConversation();
            }
        }
    };

    const getCurrentConversation = () => {
        return conversations.find(c => c.id === currentConversationId);
    };

    const updateConversationTitle = (id: string, firstMessage: string) => {
        const title = firstMessage.slice(0, 40) + (firstMessage.length > 40 ? '...' : '');
        setConversations(prev =>
            prev.map(c =>
                c.id === id ? { ...c, title } : c
            )
        );
    };

    const handleSendMessage = async () => {
        if ((!inputValue.trim() && uploadedFiles.length === 0) || isLoading) return;

        const currentConv = getCurrentConversation();
        if (!currentConv) return;

        let messageContent = inputValue;
        if (uploadedFiles.length > 0) {
            messageContent += `\n\n[Attached Files: ${uploadedFiles.map(f => f.name).join(', ')}]`;
        }

        const userMessage: Message = {
            id: Date.now().toString(),
            type: 'user',
            content: inputValue,
            timestamp: new Date(),
            files: [...uploadedFiles],
        };

        const updatedMessages = [...currentConv.messages, userMessage];

        // Update title if this is the first user message
        if (currentConv.messages.length === 1 && inputValue.trim()) {
            updateConversationTitle(currentConv.id, inputValue);
        }

        setConversations(prev =>
            prev.map(c =>
                c.id === currentConversationId
                    ? { ...c, messages: updatedMessages }
                    : c
            )
        );

        setInputValue('');
        setUploadedFiles([]);
        setIsLoading(true);
        setIsTyping(true);

        try {
            // Build message with file context
            let messageToSend = inputValue;
            if (uploadedFiles.length > 0) {
                const fileList = uploadedFiles.map(f => {
                    const ext = f.name.split('.').pop()?.toLowerCase() || '';
                    const typeMap: Record<string, string> = {
                        'pdf': 'PDF',
                        'docx': 'Word',
                        'doc': 'Word',
                        'txt': 'Text',
                        'md': 'Markdown',
                        'rst': 'reStructuredText',
                        'png': 'Image',
                        'jpg': 'Image',
                        'jpeg': 'Image',
                        'gif': 'Image',
                        'bmp': 'Image',
                        'svg': 'Image',
                        'webp': 'Image',
                    };
                    return `${f.name} (${typeMap[ext] || 'File'}, ${formatFileSize(f.size)})`;
                }).join(', ');

                messageToSend += `\n\n[Files attached: ${fileList}]\n\nNote: I've attached these files for analysis. Please let me know if you can help me analyze them or if I need to upload them to a specific location.`;
            }

            const response = await apiFetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: messageToSend,
                    session_id: currentConversationId,
                }),
            });

            if (!response.ok) {
                throw new Error('Failed to send message');
            }

            const data = await response.json();

            const assistantMessage: Message = {
                id: (Date.now() + 1).toString(),
                type: 'assistant',
                content: data.response || 'Sorry, I encountered an error.',
                timestamp: new Date(),
                sql: data.sql_executed,
                toolResults: data.tool_results,
            };

            setConversations(prev =>
                prev.map(c =>
                    c.id === currentConversationId
                        ? { ...c, messages: [...c.messages, assistantMessage] }
                        : c
                )
            );
        } catch (error) {
            console.error('Error sending message:', error);
            const errorMessage: Message = {
                id: (Date.now() + 1).toString(),
                type: 'assistant',
                content: 'Sorry, I encountered an error. Please try again.',
                timestamp: new Date(),
            };

            setConversations(prev =>
                prev.map(c =>
                    c.id === currentConversationId
                        ? { ...c, messages: [...c.messages, errorMessage] }
                        : c
                )
            );
        } finally {
            setIsLoading(false);
            setIsTyping(false);
        }
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    };

    const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files) return;

        Array.from(files).forEach(file => {
            const reader = new FileReader();
            reader.onload = (event) => {
                const content = event.target?.result as string;
                const newFile: UploadedFile = {
                    name: file.name,
                    type: file.type,
                    size: file.size,
                    content: content,
                };
                setUploadedFiles(prev => [...prev, newFile]);
            };
            reader.readAsDataURL(file);
        });

        // Reset input
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    const removeFile = (index: number) => {
        setUploadedFiles(prev => prev.filter((_, i) => i !== index));
    };

    const getFileIcon = (fileName: string) => {
        const ext = fileName.split('.').pop()?.toLowerCase();
        if (['png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg', 'webp'].includes(ext || '')) {
            return <Image className="w-4 h-4" />;
        }
        if (['pdf', 'docx', 'doc'].includes(ext || '')) {
            return <FileText className="w-4 h-4" />;
        }
        return <File className="w-4 h-4" />;
    };

    const formatFileSize = (bytes: number) => {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    };

    const currentConv = getCurrentConversation();

    return (
        <div className="flex h-screen bg-gray-50 dark:bg-gray-900">
            {/* Sidebar */}
            {sidebarOpen && (
                <div className="w-80 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex flex-col">
                    {/* Sidebar Header */}
                    <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                        <button
                            onClick={createNewConversation}
                            className="w-full flex items-center justify-center space-x-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
                        >
                            <Plus className="w-4 h-4" />
                            <span>New Conversation</span>
                        </button>
                    </div>

                    {/* Conversations List */}
                    <div className="flex-1 overflow-y-auto p-4 space-y-2">
                        {conversations.map((conv) => (
                            <div
                                key={conv.id}
                                className={`p-3 rounded-lg cursor-pointer transition-colors ${
                                    currentConversationId === conv.id
                                        ? 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800'
                                        : 'bg-gray-50 dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600'
                                }`}
                                onClick={() => setCurrentConversationId(conv.id)}
                            >
                                <div className="flex items-start justify-between">
                                    <div className="flex-1 min-w-0">
                                        <h4 className="text-sm font-medium text-gray-900 dark:text-white truncate">
                                            {conv.title}
                                        </h4>
                                        <p className="text-xs text-gray-500 dark:text-gray-400 flex items-center mt-1">
                                            <Clock className="w-3 h-3 mr-1" />
                                            {conv.timestamp.toLocaleDateString()}
                                        </p>
                                    </div>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            deleteConversation(conv.id);
                                        }}
                                        className="text-gray-400 hover:text-red-500 transition-colors"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Main Chat Area */}
            <div className="flex-1 flex flex-col">
                {/* Header */}
                <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                            <button
                                onClick={() => setSidebarOpen(!sidebarOpen)}
                                className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                            >
                                <Bot className="w-6 h-6" />
                            </button>
                            <div>
                                <h1 className="text-xl font-bold text-gray-900 dark:text-white">DevRel Agent</h1>
                                <p className="text-sm text-gray-500 dark:text-gray-400">
                                    {currentView === 'chat' ? (currentConv?.title || 'New Conversation') : 'The Deck Dashboard'}
                                </p>
                            </div>
                        </div>

                        {/* Navigation Tabs */}
                        <div className="flex items-center space-x-2 bg-gray-100 dark:bg-gray-900 rounded-lg p-1">
                            <button
                                onClick={() => setCurrentView('chat')}
                                className={`flex items-center space-x-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                                    currentView === 'chat'
                                        ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                                        : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                                }`}
                            >
                                <Bot className="w-4 h-4" />
                                <span>Chat</span>
                            </button>
                            <button
                                onClick={() => router.push('/dashboard')}
                                className={`flex items-center space-x-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                                    currentView === 'dashboard'
                                        ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                                        : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                                }`}
                            >
                                <Activity className="w-4 h-4" />
                                <span>Dashboard</span>
                            </button>
                        </div>

                        <div className="flex items-center space-x-2">
                            <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                            <span className="text-sm text-gray-600 dark:text-gray-300">Online</span>
                        </div>
                    </div>
                </div>

                {/* Content Area */}
                {currentView === 'dashboard' ? (
                    /* Dashboard View */
                    <div className="flex-1 flex flex-col">
                        <div className="flex-1 overflow-y-auto bg-gray-50 dark:bg-gray-900">
                            <div className="p-6">
                                <div className="bg-gradient-to-r from-purple-50 to-blue-50 dark:from-gray-800 dark:to-gray-900 rounded-lg p-8 mb-6">
                                    <div className="flex items-center space-x-4 mb-4">
                                        <Activity className="w-12 h-12 text-purple-600 dark:text-purple-400" />
                                        <div>
                                            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">The Deck</h2>
                                            <p className="text-gray-600 dark:text-gray-400">
                                                Real-time system health monitoring and alerting
                                            </p>
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
                                        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                                            <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Features</h3>
                                            <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                                                <li>• Error spike detection</li>
                                                <li>• Auto-diagnosis</li>
                                                <li>• Real-time alerts</li>
                                                <li>• System status</li>
                                            </ul>
                                        </div>
                                        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                                            <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Integration</h3>
                                            <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                                                <li>• ClickHouse logs</li>
                                                <li>• GitHub actions</li>
                                                <li>• Browser automation</li>
                                            </ul>
                                        </div>
                                        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                                            <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Coming Soon</h3>
                                            <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                                                <li>• Advanced analytics</li>
                                                <li>• Trend visualization</li>
                                                <li>• Custom alerts</li>
                                            </ul>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                ) : (
                    /* Chat View - Original Content */
                    <>
                {/* Messages */}
                <div className="flex-1 overflow-y-auto p-6 space-y-6">
                    {currentConv?.messages.map((message) => (
                        <div key={message.id}>
                            <MessageBubble message={message} />
                            {message.files && message.files.length > 0 && (
                                <div className="ml-10 mt-2 flex flex-wrap gap-2">
                                    {message.files.map((file, idx) => (
                                        <div
                                            key={idx}
                                            className="flex items-center space-x-2 bg-gray-100 dark:bg-gray-700 rounded-lg px-3 py-2 text-sm"
                                        >
                                            {getFileIcon(file.name)}
                                            <span className="text-gray-700 dark:text-gray-300">{file.name}</span>
                                            <span className="text-gray-500 dark:text-gray-400 text-xs">
                                                ({formatFileSize(file.size)})
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    ))}

                    {isTyping && (
                        <div className="flex items-center space-x-2 text-gray-500 dark:text-gray-400">
                            <Bot className="w-4 h-4" />
                            <div className="flex space-x-1">
                                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                            </div>
                        </div>
                    )}

                    <div ref={messagesEndRef} />
                </div>

                {/* SQL Sandbox */}
                {currentConv?.messages.some(m => m.sql) && (
                    <div className="border-t border-gray-200 dark:border-gray-700">
                        <SqlSandbox
                            sql={currentConv.messages.filter(m => m.sql).pop()?.sql || ''}
                        />
                    </div>
                )}

                {/* Input Area */}
                <div className="bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 p-4">
                    {/* Uploaded Files */}
                    {uploadedFiles.length > 0 && (
                        <div className="mb-3 flex flex-wrap gap-2">
                            {uploadedFiles.map((file, idx) => (
                                <div
                                    key={idx}
                                    className="flex items-center space-x-2 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg px-3 py-2"
                                >
                                    {getFileIcon(file.name)}
                                    <span className="text-sm text-gray-700 dark:text-gray-300">{file.name}</span>
                                    <span className="text-xs text-gray-500 dark:text-gray-400">
                                        {formatFileSize(file.size)}
                                    </span>
                                    <button
                                        onClick={() => removeFile(idx)}
                                        className="text-gray-400 hover:text-red-500 transition-colors"
                                    >
                                        <X className="w-4 h-4" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Text Input */}
                    <div className="flex items-end space-x-3">
                        <input
                            type="file"
                            ref={fileInputRef}
                            onChange={handleFileUpload}
                            className="hidden"
                            multiple
                            accept=".pdf,.docx,.doc,.txt,.md,.rst,.png,.jpg,.jpeg,.gif,.bmp,.svg,.webp"
                        />
                        <button
                            onClick={() => fileInputRef.current?.click()}
                            className="p-3 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                            title="Attach files (PDF, Word, Text, Images)"
                        >
                            <Paperclip className="w-5 h-5" />
                        </button>
                        <div className="flex-1">
                            <textarea
                                value={inputValue}
                                onChange={(e) => setInputValue(e.target.value)}
                                onKeyPress={handleKeyPress}
                                placeholder="Ask me about docs, logs, issues, or upload files for analysis..."
                                className="w-full resize-none border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-3 bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                rows={2}
                                disabled={isLoading}
                            />
                        </div>
                        <button
                            onClick={handleSendMessage}
                            disabled={isLoading || (!inputValue.trim() && uploadedFiles.length === 0)}
                            className="p-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-lg transition-colors"
                        >
                            <Send className="w-5 h-5" />
                        </button>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                        Supports: PDF, Word (.docx), Text (.txt, .md), Images (PNG, JPG, GIF, SVG)
                    </p>
                </div>
                    </>
                )}
            </div>
        </div>
    );
}
