/**
 * Decision Timeline Component
 * 
 * Core view: scrollable, append-only timeline of all system decisions.
 * Color-coded by outcome, strictly non-semantic.
 */

import React, { useEffect, useState } from 'react';
import { AuditEvent, DecisionCode, ExecutionResult } from '../types/events';

const API_URL = 'http://localhost:8000';

interface DecisionTimelineProps {
    onEventClick: (event: AuditEvent) => void;
}

export const DecisionTimeline: React.FC<DecisionTimelineProps> = ({ onEventClick }) => {
    const [events, setEvents] = useState<AuditEvent[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchEvents = async () => {
            try {
                const response = await fetch(`${API_URL}/api/events?limit=100`);
                const data = await response.json();
                setEvents(data);
                setLoading(false);
            } catch (error) {
                console.error('Failed to fetch events:', error);
                setLoading(false);
            }
        };

        fetchEvents();
        const interval = setInterval(fetchEvents, 5000); // Poll every 5s

        return () => clearInterval(interval);
    }, []);

    const getRowColor = (decision: DecisionCode, execution?: ExecutionResult): string => {
        // Strict, non-semantic color rules
        if (decision === 'NO_ACTION') return '#404040'; // Gray
        if (decision === 'AUTHORIZED_ACTION') return '#665500'; // Yellow
        if (decision === 'REJECTED_ACTION') return '#660000'; // Red
        if (execution === 'FAILED_SAFE') return '#003366'; // Blue
        return '#2a2a2a';
    };

    const formatTimestamp = (timestamp: number) => {
        return new Date(timestamp * 1000).toLocaleString('en-US', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    };

    if (loading) {
        return <div style={styles.container}>Loading events...</div>;
    }

    if (events.length === 0) {
        return (
            <div style={styles.container}>
                <div style={styles.emptyState}>
                    <p>No events yet.</p>
                    <p style={styles.emptyHint}>
                        Silence is a valid outcome. System may be correctly abstaining.
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div style={styles.container}>
            <div style={styles.header}>
                <h2>Decision Timeline</h2>
                <span style={styles.count}>{events.length} events</span>
            </div>

            <div style={styles.timeline}>
                <table style={styles.table}>
                    <thead>
                        <tr style={styles.tableHeader}>
                            <th style={styles.th}>Timestamp</th>
                            <th style={styles.th}>Trace ID</th>
                            <th style={styles.th}>Strategy</th>
                            <th style={styles.th}>Decision</th>
                            <th style={styles.th}>Execution</th>
                            <th style={styles.th}>Reason</th>
                            <th style={styles.th}>Symbol</th>
                        </tr>
                    </thead>
                    <tbody>
                        {events.map((event) => (
                            <tr
                                key={event.trace_id}
                                style={{
                                    ...styles.row,
                                    backgroundColor: getRowColor(event.decision_code, event.execution_result),
                                }}
                                onClick={() => onEventClick(event)}
                            >
                                <td style={styles.td}>{formatTimestamp(event.timestamp)}</td>
                                <td style={styles.tdMono}>{event.trace_id}</td>
                                <td style={styles.td}>{event.strategy_id || '-'}</td>
                                <td style={styles.td}>{event.decision_code}</td>
                                <td style={styles.td}>{event.execution_result || '-'}</td>
                                <td style={styles.td}>{event.reason_code}</td>
                                <td style={styles.tdMono}>{event.symbol}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <div style={styles.legend}>
                <span style={styles.legendItem}>
                    <span style={{ ...styles.legendDot, backgroundColor: '#404040' }}></span>
                    NO_ACTION
                </span>
                <span style={styles.legendItem}>
                    <span style={{ ...styles.legendDot, backgroundColor: '#665500' }}></span>
                    AUTHORIZED_ACTION
                </span>
                <span style={styles.legendItem}>
                    <span style={{ ...styles.legendDot, backgroundColor: '#660000' }}></span>
                    REJECTED_ACTION
                </span>
                <span style={styles.legendItem}>
                    <span style={{ ...styles.legendDot, backgroundColor: '#003366' }}></span>
                    FAILED_SAFE
                </span>
            </div>
        </div>
    );
};

const styles: Record<string, React.CSSProperties> = {
    container: {
        padding: '20px',
        backgroundColor: '#0a0a0a',
        minHeight: '400px',
    },
    header: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '16px',
        color: '#e0e0e0',
    },
    count: {
        fontSize: '14px',
        color: '#888',
        fontFamily: 'monospace',
    },
    timeline: {
        overflowY: 'auto',
        maxHeight: '600px',
        border: '1px solid #333',
    },
    table: {
        width: '100%',
        borderCollapse: 'collapse',
        fontSize: '13px',
        fontFamily: 'monospace',
    },
    tableHeader: {
        position: 'sticky' as const,
        top: 0,
        backgroundColor: '#1a1a1a',
        zIndex: 10,
    },
    th: {
        padding: '12px 8px',
        textAlign: 'left' as const,
        borderBottom: '2px solid #444',
        color: '#aaa',
        fontSize: '11px',
        textTransform: 'uppercase' as const,
        letterSpacing: '0.5px',
    },
    row: {
        cursor: 'pointer',
        transition: 'opacity 0.1s',
    },
    td: {
        padding: '10px 8px',
        borderBottom: '1px solid #222',
        color: '#ccc',
    },
    tdMono: {
        padding: '10px 8px',
        borderBottom: '1px solid #222',
        color: '#ccc',
        fontFamily: 'monospace',
        fontSize: '12px',
    },
    emptyState: {
        textAlign: 'center' as const,
        padding: '60px 20px',
        color: '#888',
    },
    emptyHint: {
        fontSize: '12px',
        marginTop: '8px',
        fontStyle: 'italic' as const,
    },
    legend: {
        display: 'flex',
        gap: '20px',
        marginTop: '16px',
        padding: '12px',
        backgroundColor: '#1a1a1a',
        borderRadius: '4px',
    },
    legendItem: {
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        fontSize: '12px',
        color: '#aaa',
    },
    legendDot: {
        width: '12px',
        height: '12px',
        borderRadius: '2px',
    },
};
