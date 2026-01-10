/**
 * Main App Component
 * 
 * Orchestrates all UI sections. Strictly read-only interface.
 * No controls that influence system behavior.
 */

import React, { useState } from 'react';
import { LiveStatusHeader } from './components/LiveStatusHeader';
import { DecisionTimeline } from './components/DecisionTimeline';
import { GhostExecutionDrawer } from './components/GhostExecutionDrawer';
import { MarketEventTimeline } from './components/MarketEventTimeline';
import { AuditEvent, GhostExecutionRecord } from './types/events';

function App() {
    const [selectedEvent, setSelectedEvent] = useState<AuditEvent | null>(null);
    const [ghostRecord, setGhostRecord] = useState<GhostExecutionRecord | null>(null);

    const handleEventClick = async (event: AuditEvent) => {
        setSelectedEvent(event);

        // In full implementation, fetch ghost execution record for this trace_id
        // For now, show mock data
        const mockGhostRecord: GhostExecutionRecord = {
            trace_id: event.trace_id,
            execution_mode: 'GHOST_LIVE',
            orderbook_snapshot_id: `${event.symbol}_${Math.floor(event.timestamp * 1000)}`,
            best_bid: 65210.4,
            best_ask: 65210.5,
            spread: 0.1,
            would_execute: event.execution_result === 'SUCCESS',
            fill_estimate: 'FULL',
            order_type: 'LIMIT',
            quantity: 0.01,
            price: 65210.5,
        };

        setGhostRecord(mockGhostRecord);
    };

    const handleCloseDrawer = () => {
        setSelectedEvent(null);
        setGhostRecord(null);
    };

    return (
        <div style={styles.app}>
            <LiveStatusHeader />

            <main style={styles.main}>
                <div style={styles.section}>
                    <MarketEventTimeline />
                </div>

                <div style={styles.section}>
                    <DecisionTimeline onEventClick={handleEventClick} />
                </div>
            </main>

            <GhostExecutionDrawer
                record={ghostRecord}
                onClose={handleCloseDrawer}
            />

            <footer style={styles.footer}>
                <p style={styles.footerText}>
                    Live-Run Observability UI v1.0 | System v1.0 FROZEN | Read-Only Interface
                </p>
                <p style={styles.footerHint}>
                    This UI does not control the system. It renders truth.
                </p>
            </footer>
        </div>
    );
}

const styles: Record<string, React.CSSProperties> = {
    app: {
        minHeight: '100vh',
        backgroundColor: '#000',
        color: '#e0e0e0',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    },
    main: {
        maxWidth: '1600px',
        margin: '0 auto',
        padding: '0',
    },
    section: {
        marginBottom: '0',
    },
    footer: {
        marginTop: '40px',
        padding: '24px',
        borderTop: '1px solid #222',
        textAlign: 'center' as const,
        backgroundColor: '#0a0a0a',
    },
    footerText: {
        margin: 0,
        fontSize: '12px',
        color: '#666',
        fontFamily: 'monospace',
    },
    footerHint: {
        margin: '8px 0 0',
        fontSize: '11px',
        color: '#444',
        fontStyle: 'italic' as const,
    },
};

export default App;
