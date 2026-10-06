"use client";

import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, Paperclip, X, Plus, Clock, Trash2, FileText, Image, File, Activity, BookOpen, ShieldCheck, PanelLeftClose, PanelLeftOpen, Sparkles, ArrowUpRight, Command, Network, Radio, TerminalSquare, Orbit, ChevronDown, Database } from 'lucide-react';
import { MessageBubble } from './MessageBubble';
import { SqlSandbox } from './SqlSandbox';
import { AppHeader } from './AppHeader';
import { apiFetch } from '../lib/api';
import { getIdentity, getProject, IDENTITY_EVENT } from '../lib/auth';

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
}

interface Conversation {
    id: string;
    title: string;
    messages: Message[];
    timestamp: Date;
}

function newSessionId(): string {
    return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function conversationStorageKey(): string {
    const identity = getIdentity();
    const project = getProject();
    return `devrel-conversations:${encodeURIComponent(identity.workspace)}:${project?.id ?? 'workspace'}`;
}

function parseStoredConversation(value: unknown): Conversation | null {
    if (!value || typeof value !== 'object') return null;
    const item = value as Partial<Conversation>;
    if (typeof item.id !== 'string' || !Array.isArray(item.messages)) return null;

    const messages = item.messages.flatMap((message): Message[] => {
        if (!message || typeof message !== 'object') return [];
        const entry = message as Partial<Message>;
        if (typeof entry.id !== 'string' || (entry.type !== 'user' && entry.type !== 'assistant') || typeof entry.content !== 'string') return [];
        const files = Array.isArray(entry.files)
            ? entry.files.flatMap((file) => file && typeof file.name === 'string'
                ? [{ name: file.name, type: typeof file.type === 'string' ? file.type : '', size: typeof file.size === 'number' && Number.isFinite(file.size) && file.size >= 0 ? file.size : 0 }]
                : [])
            : undefined;
        const timestamp = new Date(entry.timestamp ?? Date.now());
        return [{ ...entry, files, timestamp: Number.isNaN(timestamp.getTime()) ? new Date() : timestamp } as Message];
    });

    const timestamp = new Date(item.timestamp ?? Date.now());
    return {
        id: item.id,
        title: typeof item.title === 'string' ? item.title : 'Conversation',
        messages,
        timestamp: Number.isNaN(timestamp.getTime()) ? new Date() : timestamp,
    };
}

function createWelcomeConversation(): Conversation {
    return {
        id: newSessionId(),
        title: 'New conversation',
        messages: [],
        timestamp: new Date(),
    };
}

export function FullChat() {
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
    const [inputValue, setInputValue] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isTyping, setIsTyping] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const [conversationSearch, setConversationSearch] = useState('');
    const [backendReady, setBackendReady] = useState<boolean | null>(null);
    const [storageError, setStorageError] = useState(false);
    const [fileError, setFileError] = useState<string | null>(null);
    const [isInitialized, setIsInitialized] = useState(false);
    const storageKeyRef = useRef<string | null>(null);

    // Restore history per workspace/project so switching tenant context never
    // carries a previous scope's locally cached conversations into the new one.
    useEffect(() => {
        if (window.innerWidth <= 560) setSidebarOpen(false);
    }, []);

    useEffect(() => {
        const restoreForCurrentScope = (consumeDeepLink = false) => {
            const key = conversationStorageKey();
            if (storageKeyRef.current === key) return;
            storageKeyRef.current = key;
            setIsInitialized(false);
            try {
                const saved = window.localStorage.getItem(key);
                if (saved) {
                    const parsed: unknown = JSON.parse(saved);
                    if (!Array.isArray(parsed)) throw new Error('Saved chat history is not a list.');
                    const convs = parsed
                        .map(parseStoredConversation)
                        .filter((conversation): conversation is Conversation => conversation !== null)
                        .map((conversation) => {
                            const onlyMessage = conversation.messages[0];
                            if (conversation.messages.length === 1 && onlyMessage?.type === 'assistant' && onlyMessage.content.startsWith('Welcome to DevRelAgent.')) {
                                return { ...conversation, messages: [] };
                            }
                            return conversation;
                        });
                    if (convs.length > 0) {
                        setConversations(convs);
                        setCurrentConversationId(convs[0].id);
                    } else {
                        const welcome = createWelcomeConversation();
                        setConversations([welcome]);
                        setCurrentConversationId(welcome.id);
                    }
                    setStorageError(false);
                    setIsInitialized(true);
                } else {
                    const welcome = createWelcomeConversation();
                    setConversations([welcome]);
                    setCurrentConversationId(welcome.id);
                    setIsInitialized(true);
                }
            } catch {
                try { window.localStorage.removeItem(key); } catch { /* Storage can be blocked. */ }
                const welcome = createWelcomeConversation();
                setConversations([welcome]);
                setCurrentConversationId(welcome.id);
                setStorageError(true);
                setIsInitialized(true);
            }

            if (consumeDeepLink) {
                const query = new URLSearchParams(window.location.search).get('q');
                if (query) {
                    const fresh = createWelcomeConversation();
                    const saved = (() => {
                        try { return window.localStorage.getItem(key); } catch { return null; }
                    })();
                    const previous = saved ? (() => {
                        try {
                            const parsed: unknown = JSON.parse(saved);
                            return Array.isArray(parsed)
                                ? parsed.map(parseStoredConversation).filter((conversation): conversation is Conversation => conversation !== null)
                                : [];
                        } catch { return []; }
                    })() : [];
                    setConversations([fresh, ...previous]);
                    setCurrentConversationId(fresh.id);
                    setInputValue(query);
                    window.history.replaceState({}, '', '/');
                }
            }
        };

        restoreForCurrentScope(true);
        const handleIdentityChange = () => restoreForCurrentScope();
        window.addEventListener(IDENTITY_EVENT, handleIdentityChange);
        return () => window.removeEventListener(IDENTITY_EVENT, handleIdentityChange);
    }, []);

    useEffect(() => {
        if (conversations.length === 0 || storageKeyRef.current === null || !isInitialized) return;
        try {
            window.localStorage.setItem(storageKeyRef.current ?? conversationStorageKey(), JSON.stringify(conversations));
            setStorageError(false);
        } catch {
            setStorageError(true);
        }
    }, [conversations, isInitialized]);

    useEffect(() => {
        let cancelled = false;
        void apiFetch('/health')
            .then((response) => { if (!cancelled) setBackendReady(response.ok); })
            .catch(() => { if (!cancelled) setBackendReady(false); });
        return () => { cancelled = true; };
    }, []);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [currentConversationId, conversations]);

    const createNewConversation = () => {
        const newConv = createWelcomeConversation();
        setConversations(prev => [newConv, ...prev.filter((conversation) => conversation.id !== newConv.id)]);
        setCurrentConversationId(newConv.id);
        setUploadedFiles([]);
        if (window.innerWidth <= 560) setSidebarOpen(false);
    };

    const deleteConversation = (id: string) => {
        const remaining = conversations.filter((conversation) => conversation.id !== id);
        if (currentConversationId === id) {
            if (remaining.length > 0) {
                setConversations(remaining);
                setCurrentConversationId(remaining[0].id);
            } else {
                const fresh = createWelcomeConversation();
                setConversations([fresh]);
                setCurrentConversationId(fresh.id);
            }
        } else {
            setConversations(remaining);
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

        const messageContent = inputValue.trim();
        const requestStorageKey = storageKeyRef.current ?? conversationStorageKey();

        const userMessage: Message = {
            id: newSessionId(),
            type: 'user',
            content: messageContent || (uploadedFiles.length > 0 ? 'Please help me with these selected file(s).' : ''),
            timestamp: new Date(),
            files: [...uploadedFiles],
        };

        const updatedMessages = [...currentConv.messages, userMessage];

        // Update title if this is the first user message.
        if (currentConv.messages.length === 0 && (inputValue.trim() || uploadedFiles.length > 0)) {
            updateConversationTitle(currentConv.id, inputValue.trim() || 'Selected file attachments');
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
        if (window.innerWidth <= 560) setSidebarOpen(false);
        setIsLoading(true);
        setIsTyping(true);

        try {
            const attachmentNote = uploadedFiles.length > 0
                ? `\n\nSelected files (not uploaded): ${uploadedFiles.map((file) => file.name).join(', ')}. Their contents are not available to the agent.`
                : '';
            const messageToSend = `${messageContent || 'Please help me with the selected file(s).'}${attachmentNote}`;

            const response = await apiFetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: messageToSend, session_id: currentConversationId }),
            });

            if (!response.ok) {
                let detail = `The request failed (HTTP ${response.status}).`;
                try {
                    const payload = await response.json();
                    if (typeof payload.detail === 'string') detail = payload.detail;
                } catch { /* Keep the status message when the response is not JSON. */ }
                throw new Error(detail);
            }

            const data = await response.json();

            const assistantMessage: Message = {
                id: newSessionId(),
                type: 'assistant',
                content: data.response || 'Sorry, I encountered an error.',
                timestamp: new Date(),
                sql: data.sql_executed,
                toolResults: data.tool_calls ?? data.tool_results,
            };
            setConversations(prev => {
                if (storageKeyRef.current !== requestStorageKey) return prev;
                return prev.map(c =>
                    c.id === currentConv.id
                        ? { ...c, messages: [...c.messages, assistantMessage] }
                        : c
                );
            });
        } catch (error) {
            console.error('Error sending message:', error);
            const errorMessage: Message = {
                id: newSessionId(),
                type: 'assistant',
                content: error instanceof Error ? `I couldn't complete that request. ${error.message}` : 'I could not complete that request. Please check the backend connection and try again.',
                timestamp: new Date(),
            };

            setConversations(prev => {
                if (storageKeyRef.current !== requestStorageKey) return prev;
                return prev.map(c =>
                    c.id === currentConv.id
                        ? { ...c, messages: [...c.messages, errorMessage] }
                        : c
                );
            });
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
        const supported = new Set(['pdf', 'docx', 'doc', 'txt', 'md', 'rst', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg', 'webp']);
        const candidates = Array.from(files).filter((file) => {
            const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
            return supported.has(extension) && file.size <= 5 * 1024 * 1024;
        });
        const availableSlots = Math.max(0, 10 - uploadedFiles.length);
        const accepted = candidates.slice(0, availableSlots);
        setFileError(accepted.length !== files.length
            ? 'Up to 10 PDF, Word, text or image files (5 MB each) can be selected. Only filenames are sent with your message; file contents are not uploaded or analyzed.'
            : null);
        setUploadedFiles((current) => [...current, ...accepted.map((file) => ({ name: file.name, type: file.type, size: file.size }))]);
        if (fileInputRef.current) fileInputRef.current.value = '';
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
        <div className="chat-app-shell">
            <AppHeader active="chat" title="Command center" subtitle="Engineering intelligence · Live workspace" />
            <div className="chat-workspace-layout">
                {/* Sidebar */}
                {sidebarOpen && (
                <>
                <div className="chat-sidebar-backdrop" aria-hidden="true" onClick={() => setSidebarOpen(false)} />
                <aside className="chat-sidebar">
                    <div className="chat-sidebar-top">
                        <div className="chat-sidebar-actions">
                            <button type="button" onClick={createNewConversation} className="chat-new-thread"><Plus size={16} /><span>New conversation</span></button>
                            <button type="button" className="chat-sidebar-close" aria-label="Close conversation sidebar" onClick={() => setSidebarOpen(false)}><X size={16} /></button>
                        </div>
                        <label className="conversation-search"><Activity size={15} /><input aria-label="Search conversations" placeholder="Find a conversation" value={conversationSearch} onChange={(event) => setConversationSearch(event.target.value)} /><span>⌘ K</span></label>
                    </div>
                    <div className="chat-sidebar-label">YOUR RECENT WORK</div>
                    <div className="chat-thread-list" aria-label="Recent conversations">
                        {conversations.filter((conversation) => conversation.title.toLowerCase().includes(conversationSearch.toLowerCase())).map((conv) => (
                            <div key={conv.id} className="chat-thread-row">
                                <button
                                    type="button"
                                    className={`chat-thread ${currentConversationId === conv.id ? 'chat-thread-active' : ''}`}
                                    aria-current={currentConversationId === conv.id ? 'true' : undefined}
                                    onClick={() => {
                                        setCurrentConversationId(conv.id);
                                        if (window.innerWidth <= 560) setSidebarOpen(false);
                                    }}
                                >
                                    <span className="chat-thread-copy">
                                        <strong className="chat-thread-name">{conv.title}</strong>
                                        <small className="chat-thread-date"><Clock size={12} />{Number.isNaN(conv.timestamp.getTime()) ? 'Saved conversation' : conv.timestamp.toLocaleDateString()}</small>
                                    </span>
                                </button>
                                <button type="button" className="chat-thread-delete" aria-label={`Delete ${conv.title}`} title={`Delete ${conv.title}`} onClick={() => deleteConversation(conv.id)}>
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        ))}
                    </div>
                    {conversations.length === 0 && <p className="chat-sidebar-empty">Your conversations will appear here.</p>}
                    <button type="button" className="chat-sidebar-guide" onClick={() => window.open('/guide', '_blank', 'noopener,noreferrer')}><BookOpen size={15} /><span>Explore the product guide</span></button>
                    <div className="chat-sidebar-bottom"><ShieldCheck size={15} /><span>Review high-impact actions in Approvals</span></div>
                </aside>
                </>
                )}

                {/* Main Chat Area */}
                <main className="chat-main">
                    <div className="chat-main-heading">
                        <div className="chat-heading-title">
                            <button type="button" className="chat-sidebar-toggle" onClick={() => setSidebarOpen((open) => !open)} aria-label={sidebarOpen ? 'Hide conversations' : 'Show conversations'} aria-expanded={sidebarOpen}>
                                {sidebarOpen ? <PanelLeftClose size={17} /> : <PanelLeftOpen size={17} />}
                            </button>
                            <div className="chat-title-copy"><div className="chat-title-overline"><span className="chat-title-live-dot" /> DEVREL AGENT <span className="chat-title-separator">/</span> ENGINEERING OPS</div><h1>{currentConv?.title || 'New conversation'}</h1><p>Ask a question or describe an issue to investigate.</p></div>
                        </div>
                        <div className="chat-heading-status">
                            <span className={`backend-indicator ${backendReady === true ? 'backend-online' : backendReady === false ? 'backend-offline' : ''}`}><i />{backendReady === true ? 'API CONNECTED' : backendReady === false ? 'API OFFLINE' : 'CONNECTING'}</span>
                            <span className="chat-scope-badge"><ShieldCheck size={13} /> PROJECT SCOPE <ChevronDown size={12} /></span>
                        </div>
                    </div>
                    {/* Messages */}
                    <div className={`chat-messages ${currentConv?.messages.length === 0 ? 'chat-messages-welcome' : ''}`}>
                        {currentConv?.messages.length === 0 && (
                            <section className="chat-welcome-panel" aria-label="Start a conversation">
                                <div className="chat-welcome-grid">
                                <div className="chat-welcome-copy">
                                    <p className="chat-welcome-kicker"><span /> DEVREL AGENT <span className="welcome-kicker-dash">/</span> INTELLIGENCE CORE</p>
                                    <h2>Engineering,<br /><span>in full signal.</span></h2>
                                    <p className="chat-welcome-description">Your operational copilot for understanding systems, tracing incidents, and moving from question to confident action.</p>
                                </div>
                                <div className="chat-system-preview" aria-label="DevRelAgent security model">
                                    <div className="system-preview-header"><span><Activity size={13} /> SYSTEM TOPOLOGY</span><span className="system-preview-index">SYS / 01</span></div>
                                    <div className="system-orbit-stage">
                                        <span className="system-orbit system-orbit-a" /><span className="system-orbit system-orbit-b" />
                                        <span className="system-node system-node-context"><Database size={13} /> CONTEXT</span>
                                        <span className="system-node system-node-tools"><TerminalSquare size={13} /> TOOLS</span>
                                        <span className="system-node system-node-approval"><ShieldCheck size={13} /> APPROVAL</span>
                                        <span className="system-core"><Orbit size={20} /></span>
                                    </div>
                                    <div className="system-preview-divider" />
                                    <div className="system-preview-row"><span>CONTEXT BOUNDARY</span><strong>PROJECT SCOPED</strong></div>
                                    <div className="system-preview-row"><span>HIGH-IMPACT ACTIONS</span><strong>HUMAN REVIEW</strong></div>
                                </div>
                                </div>
                                <div className="chat-command-label"><span>CHOOSE AN OPERATION</span><span>01 — 03</span></div>
                                <div className="chat-suggestion-grid">
                                    <button type="button" onClick={() => setInputValue('Help me understand the architecture of this project.')}><span className="suggestion-icon suggestion-icon-cyan"><Network size={17} /></span><span><strong>Map the system</strong><small>Understand architecture & dependencies</small></span><ArrowUpRight size={15} /></button>
                                    <button type="button" onClick={() => setInputValue('Help me investigate a service issue and identify useful evidence.')}><span className="suggestion-icon suggestion-icon-amber"><Radio size={17} /></span><span><strong>Investigate a signal</strong><small>Trace an incident to its source</small></span><ArrowUpRight size={15} /></button>
                                    <button type="button" onClick={() => setInputValue('Help me find the right documentation for my question.')}><span className="suggestion-icon suggestion-icon-violet"><TerminalSquare size={17} /></span><span><strong>Query the knowledge base</strong><small>Find precise technical guidance</small></span><ArrowUpRight size={15} /></button>
                                </div>
                                <div className="chat-safety-line"><ShieldCheck size={14} /><span>PROJECT-SCOPED CONTEXT</span><i /> <span>HIGH-IMPACT ACTIONS REQUIRE APPROVAL</span></div>
                            </section>
                        )}
                        <div className="chat-conversation-stream">
                    {storageError && <div className="chat-inline-notice" role="status">Conversation history could not be saved to this browser. You can continue chatting, but it may not persist after refresh.</div>}
                    {currentConv?.messages.map((message) => (
                        <div key={message.id}>
                            <MessageBubble message={message} />
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
                    <div className="chat-composer-wrap">
                        {fileError && <div className="chat-inline-notice" role="alert">{fileError}</div>}
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
                                        type="button"
                                        onClick={() => removeFile(idx)}
                                        aria-label={`Remove ${file.name}`}
                                        className="text-gray-400 hover:text-red-500 transition-colors"
                                    >
                                        <X className="w-4 h-4" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Text Input */}
                    <div className="chat-composer">
                        <input
                            type="file"
                            ref={fileInputRef}
                            onChange={handleFileUpload}
                            className="hidden"
                            multiple
                            accept=".pdf,.docx,.doc,.txt,.md,.rst,.png,.jpg,.jpeg,.gif,.bmp,.svg,.webp"
                        />
                        <button type="button" onClick={() => fileInputRef.current?.click()}
                            className="chat-attach-button"
                            aria-label="Attach files (filenames only; contents are not uploaded)"
                            title="Only filenames are included; file contents are not sent"
                        >
                            <Paperclip className="w-5 h-5" />
                        </button>
                        <div className="flex-1">
                            <textarea
                                aria-label="Message"
                                value={inputValue}
                                onChange={(e) => setInputValue(e.target.value)}
                                onKeyDown={handleKeyPress}
                                placeholder="Ask about docs, logs, or issues. Selected file names are included, not file contents..."
                                className="chat-composer-input"
                                rows={2}
                                disabled={isLoading}
                            />
                        </div>
                        <button
                            type="button"
                            onClick={handleSendMessage}
                            disabled={isLoading || (!inputValue.trim() && uploadedFiles.length === 0)}
                            className="chat-send-button"
                            aria-label="Send message"
                        >
                            <Send className="w-5 h-5" />
                        </button>
                    </div>
                        <p className="chat-composer-footnote"><span><ShieldCheck size={12} /> Your workspace context stays scoped to this project</span><span><Command size={12} /> Enter to send · Shift + Enter for a new line</span></p>
                    </div>
                </main>
            </div>
        </div>
    );
}
