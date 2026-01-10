/**
 * Ghost Execution Drawer Component
 * 
 * Shows detailed ghost execution outcome when user clicks a timeline event.
 * Reveals market reality: spread, fill estimate, reject reason.
 */

import React from 'react';
import { GhostExecutionRecord } from '../types/events';

interface GhostExecutionDrawerProps {
    record: GhostExecutionRecord | null;
    onClose: () => void;
}

export const GhostExecutionDrawer: React.FC<GhostExecutionDrawerProps> = ({ record, onClose }) => {
    if (!record) return null;

    const getFillColor = (estimate: string): string => {
        if (estimate === 'FULL') return '#006600';
        if (estimate === 'PARTIAL') return '#666600';
        return '#666666';
    };

    return (
        <div style={styles.overlay} onClick={onClose}>
            <div style={styles.drawer} onClick={(e) => e.stopPropagation()}>
                <div style={styles.header}>
                    <h3 style={styles.title}>Ghost Execution Detail</h3>
                    <button style={styles.closeButton} onClick={onClose}>×</button>
                </div>

                <div style={styles.content}>
                    {/* Execution Mode */}
                    <div style={styles.section}>
                        <div style={styles.label}>Execution Mode</div>
                        <div style={styles.value}>{record.execution_mode}</div>
                    </div>

                    {/* Order Details */}
                    <div style={styles.section}>
                        <div style={styles.sectionTitle}>Order Details</div>
                        {record.order_type && (
                            <div style={styles.row}>
                                <span style={styles.label}>Type:</span>
                                <span style={styles.value}>{record.order_type}</span>
                            </div>
                        )}
                        {record.quantity && (
                            <div style={styles.row}>
                                <span style={styles.label}>Quantity:</span>
                                <span style={styles.valueMono}>{record.quantity}</span>
                            </div>
                        )}
                        {record.price && (
                            <div style={styles.row}>
                                <span style={styles.label}>Price:</span>
                                <span style={styles.valueMono}>{record.price.toFixed(2)}</span>
                            </div>
                        )}
                    </div>

                    {/* Market State */}
                    <div style={styles.section}>
                        <div style={styles.sectionTitle}>Market State</div>
                        <div style={styles.row}>
                            <span style={styles.label}>Best Bid:</span>
                            <span style={styles.valueMono}>{record.best_bid.toFixed(2)}</span>
                        </div>
                        <div style={styles.row}>
                            <span style={styles.label}>Best Ask:</span>
                            <span style={styles.valueMono}>{record.best_ask.toFixed(2)}</span>
                        </div>
                        <div style={styles.row}>
                            <span style={styles.label}>Spread:</span>
                            <span style={styles.valueMono}>{record.spread.toFixed(2)}</span>
                        </div>
                    </div>

                    {/* Execution Outcome */}
                    <div style={styles.section}>
                        <div style={styles.sectionTitle}>Execution Outcome</div>
                        <div style={styles.row}>
                            <span style={styles.label}>Would Execute:</span>
                            <span style={{
                                ...styles.value,
                                color: record.would_execute ? '#00cc00' : '#cc0000'
                            }}>
                                {record.would_execute ? 'YES' : 'NO'}
                            </span>
                        </div>
                        <div style={styles.row}>
                            <span style={styles.label}>Fill Estimate:</span>
                            <span style={{
                                ...styles.value,
                                backgroundColor: getFillColor(record.fill_estimate),
                                padding: '2px 8px',
                                borderRadius: '3px'
                            }}>
                                {record.fill_estimate}
                            </span>
                        </div>
                        {record.reject_reason && (
                            <div style={styles.row}>
                                <span style={styles.label}>Reject Reason:</span>
                                <span style={{ ...styles.value, color: '#ff6666' }}>
                                    {record.reject_reason}
                                </span>
                            </div>
                        )}
                    </div>

                    {/* Snapshot Reference */}
                    <div style={styles.section}>
                        <div style={styles.label}>Snapshot ID</div>
                        <div style={styles.valueMonoSmall}>{record.orderbook_snapshot_id}</div>
                    </div>

                    {/* Trace ID */}
                    <div style={styles.section}>
                        <div style={styles.label}>Trace ID</div>
                        <div style={styles.valueMonoSmall}>{record.trace_id}</div>
                    </div>
                </div>

                <div style={styles.footer}>
                    <p style={styles.footerText}>
                        This is ghost execution. No real orders were placed.
                    </p>
                </div>
            </div>
        </div>
    );
};

const styles: Record<string, React.CSSProperties> = {
    overlay: {
        position: 'fixed' as const,
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        display: 'flex',
        justifyContent: 'flex-end',
        zIndex: 1000,
    },
    drawer: {
        width: '500px',
        backgroundColor: '#1a1a1a',
        color: '#e0e0e0',
        display: 'flex',
        flexDirection: 'column' as const,
        borderLeft: '1px solid #333',
    },
    header: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '20px',
        borderBottom: '1px solid #333',
    },
    title: {
        margin: 0,
        fontSize: '18px',
        fontWeight: 500,
    },
    closeButton: {
        background: 'none',
        border: 'none',
        color: '#888',
        fontSize: '32px',
        cursor: 'pointer',
        padding: 0,
        width: '32px',
        height: '32px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
    },
    content: {
        flex: 1,
        overflowY: 'auto' as const,
        padding: '20px',
    },
    section: {
        marginBottom: '24px',
    },
    sectionTitle: {
        fontSize: '12px',
        textTransform: 'uppercase' as const,
        color: '#888',
        marginBottom: '12px',
        letterSpacing: '0.5px',
    },
    row: {
        display: 'flex',
        justifyContent: 'space-between',
        padding: '8px 0',
        borderBottom: '1px solid #2a2a2a',
    },
    label: {
        fontSize: '13px',
        color: '#888',
    },
    value: {
        fontSize: '13px',
        color: '#e0e0e0',
        fontWeight: 500,
    },
    valueMono: {
        fontSize: '13px',
        color: '#e0e0e0',
        fontFamily: 'monospace',
        fontWeight: 500,
    },
    valueMonoSmall: {
        fontSize: '11px',
        color: '#aaa',
        fontFamily: 'monospace',
        wordBreak: 'break-all' as const,
    },
    footer: {
        padding: '16px 20px',
        borderTop: '1px solid #333',
        backgroundColor: '#0f0f0f',
    },
    footerText: {
        margin: 0,
        fontSize: '12px',
        color: '#666',
        fontStyle: 'italic' as const,
    },
};
