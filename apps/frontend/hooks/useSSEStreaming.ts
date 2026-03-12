/**
 * useSSEStreaming Hook
 *
 * Custom hook for handling Server-Sent Events (SSE) streaming
 * from the DevRelAgent chat API.
 *
 * Features:
 * - Automatic reconnection
 * - Event type handling
 * - Error recovery
 * - Abort capability
 * - Progress tracking
 */

import { useCallback, useRef, useState } from 'react';

interface SSEChunk {
    type: 'session_start' | 'token' | 'tool_call' | 'explanation' | 'error' | 'done';
    content?: string;
    tool_name?: string;
    data?: any;
    error?: string;
    session_id?: string;
    response?: string;
    explanation?: any;
}

interface UseSSEStreamingOptions {
    apiUrl?: string;
    reconnectInterval?: number;
    maxReconnectAttempts?: number;
}

interface UseSSEStreamingResult {
    streamMessage: (
        message: string,
        sessionId: string,
        onChunk: (chunk: SSEChunk) => void
    ) => Promise<void>;
    abortStream: () => void;
    isStreaming: boolean;
    error: string | null;
}

export function useSSEStreaming(options: UseSSEStreamingOptions = {}): UseSSEStreamingResult {
    const {
        apiUrl = 'http://localhost:8000',
        reconnectInterval = 3000,
        maxReconnectAttempts = 3,
    } = options;

    const [isStreaming, setIsStreaming] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const abortControllerRef = useRef<AbortController | null>(null);

    const streamMessage = useCallback(async (
        message: string,
        sessionId: string,
        onChunk: (chunk: SSEChunk) => void
    ): Promise<void> => {
        setIsStreaming(true);
        setError(null);

        // Create new AbortController for this request
        abortControllerRef.current = new AbortController();

        const url = new URL(`${apiUrl}/chat/stream`);
        url.searchParams.append('message', message);
        url.searchParams.append('session_id', sessionId);
        url.searchParams.append('include_tool_calls', 'true');

        let reconnectAttempts = 0;

        const connect = async (): Promise<void> => {
            return new Promise((resolve, reject) => {
                const eventSource = new EventSource(url.toString());

                let timeoutId: NodeJS.Timeout;

                // Set timeout for connection
                timeoutId = setTimeout(() => {
                    eventSource.close();
                    reject(new Error('Connection timeout'));
                }, 30000); // 30 second timeout

                eventSource.onopen = () => {
                    clearTimeout(timeoutId);
                    reconnectAttempts = 0; // Reset on successful connection
                };

                eventSource.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        onChunk(data);

                        if (data.type === 'done') {
                            eventSource.close();
                            resolve();
                        }
                    } catch (error) {
                        console.error('Error parsing SSE data:', error);
                    }
                };

                eventSource.onerror = (error) => {
                    clearTimeout(timeoutId);
                    eventSource.close();

                    if (reconnectAttempts < maxReconnectAttempts) {
                        reconnectAttempts++;
                        console.log(`SSE connection lost, reconnecting (${reconnectAttempts}/${maxReconnectAttempts})...`);

                        setTimeout(() => {
                            connect().then(resolve).catch(reject);
                        }, reconnectInterval);
                    } else {
                        reject(new Error('Max reconnection attempts reached'));
                    }
                };

                // Handle abort
                abortControllerRef.current?.signal.addEventListener('abort', () => {
                    clearTimeout(timeoutId);
                    eventSource.close();
                    reject(new Error('Stream aborted'));
                });
            });
        };

        try {
            await connect();
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown streaming error';
            setError(errorMessage);
            onChunk({
                type: 'error',
                error: errorMessage
            });
        } finally {
            setIsStreaming(false);
        }
    }, [apiUrl, maxReconnectAttempts, reconnectInterval]);

    const abortStream = useCallback(() => {
        abortControllerRef.current?.abort();
        setIsStreaming(false);
        setError(null);
    }, []);

    return {
        streamMessage,
        abortStream,
        isStreaming,
        error,
    };
}
