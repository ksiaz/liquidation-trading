/**
 * Market Event Timeline - Peak Pressure Two-Panel UI
 * 
 * Panel A: Raw Market Feed (NO INTERPRETATION)
 * Panel B: Promoted Structural Events (Peak Pressure only)
 * 
 * Authority: Peak Pressure Specification + Executive Approval
 */

import React, { useEffect, useState } from 'react';

const API_URL = 'http://localhost:8000';

interface PeakPressureEvent {
    event_id: string;
    symbol: string;
    timestamp: number;
    window_size: number;
    dominant_side: string;
    stress_sources: string[];
    metrics: {
        abs_flow: number;
        trade_count: number;
        large_trade_count: number;
        liq_count: number;
        compressed: boolean;
        expanded: boolean;
        body_ratio: number;
        oi_delta: number;
    };
}

interface PeakPressureStats {
    counters: {
        total_windows_processed: number;
        peak_pressure_count: number;
        flow_surge_failed: number;
        large_trade_failed: number;
        compression_failed: number;
        stress_failed: number;
        baseline_not_warm: number;
    };
    peak_pressure_count: number;
    windows_processed: number;
    condition_failures: {
        baseline_not_warm: number;
        flow_surge: number;
        large_trade: number;
        compression: number;
        stress: number;
    };
    baselines_active: number;
    baselines_warm: number;
    baselines_ready?: string;  // "X / Y" format
    ingestion_health?: string;  // "OK" | "DEGRADED" | "UNKNOWN" | "STARTING"
    dropped_events?: any;
    ingested_events?: any;
    liquidation_buffers?: Record<string, number>;
    zero_reason?: string;
}

export const MarketEventTimeline: React.FC = () => {
    const [peakPressureEvents, setPeakPressureEvents] = useState<PeakPressureEvent[]>([]);
    const [stats, setStats] = useState<PeakPressureStats | null>(null);
    const [rawTrades, setRawTrades] = useState<any[]>([]);
    const [rawLiqs, setRawLiqs] = useState<any[]>([]);
    const [showRawEvents, setShowRawEvents] = useState(false);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            try {
                // Fetch Peak Pressure events
                const ppResponse = await fetch(`${API_URL}/api/events/peak_pressure?limit=50`);
                const ppData = await ppResponse.json();
                setPeakPressureEvents(ppData);

                // Fetch stats
                const statsResponse = await fetch(`${API_URL}/api/market/stats`);
                const statsData = await statsResponse.json();
                setStats(statsData);

                // Fetch raw events if panel open
                if (showRawEvents) {
                    const rawResponse = await fetch(`${API_URL}/api/market/events?limit=100`);
                    const rawData = await rawResponse.json();
                    setRawTrades(rawData.filter((e: any) => e.type === 'TRADE'));
                    setRawLiqs(rawData.filter((e: any) => e.type === 'LIQUIDATION'));
                }

                setLoading(false);
            } catch (error) {
                console.error('Failed to fetch Peak Pressure data:', error);
                setLoading(false);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 2000);

        return () => clearInterval(interval);
    }, [showRawEvents]);

    if (loading || !stats) {
        return <div style={styles.container}>Loading Peak Pressure detector...</div>;
    }

    return (
        <div style={styles.container}>
            {/* Diagnostics Bar */}
            <div style={styles.diagnostics}>
                <div style={styles.diagItem}>
                    <span style={styles.diagLabel}>Windows Processed:</span>
                    <span style={styles.diagValue}>{stats.windows_processed.toLocaleString()}</span>
                </div>
                <div style={styles.diagItem}>
                    <span style={styles.diagLabel}>Peak Pressure Events:</span>
                    <span style={styles.diagValue}>{stats.peak_pressure_count}</span>
                </div>

                {/* MANDATORY: Baseline Warmup Indicator */}
                <div style={styles.diagItem}>
                    <span style={styles.diagLabel}>Baselines ready:</span>
                    <span style={{
                        ...styles.diagValue,
                        color: stats.baselines_warm === stats.baselines_active ? '#00ff00' : '#ffaa00'
                    }}>
                        {stats.baselines_ready || `${stats.baselines_warm} / ${stats.baselines_active}`}
                    </span>
                </div>

                {/* Ingestion Health Indicator */}
                {stats.ingestion_health && (
                    <div style={styles.diagItem}>
                        <span style={styles.diagLabel}>Ingestion Health:</span>
                        <span style={{
                            ...styles.diagValue,
                            color: stats.ingestion_health === 'OK' ? '#00ff00' :
                                stats.ingestion_health === 'DEGRADED' ? '#ff5500' :
                                    stats.ingestion_health === 'STARTING' ? '#ffaa00' : '#888'
                        }}>
                            {stats.ingestion_health}
                        </span>
                    </div>
                )}

                {/* Liquidation Buffer Diagnostic */}
                <div style={styles.diagItem}>
                    <span style={styles.diagLabel}>Active Liq Buffers:</span>
                    <span style={styles.diagValue}>
                        {stats.liquidation_buffers ?
                            Object.entries(stats.liquidation_buffers).length > 0 ?
                                Object.entries(stats.liquidation_buffers)
                                    .map(([sym, count]) => `${sym}:${count}`)
                                    .join(', ')
                                : 'None'
                            : '0'
                        }
                    </span>
                </div>
            </div>

            {/* PANEL B: Promoted Structural Events */}
            <div style={styles.panel}>
                <div style={styles.panelHeader}>
                    <h3 style={styles.panelTitle}>Promoted Structural Events</h3>
                    <span style={styles.panelSubtitle}>
                        Peak Pressure (multi-stream coincidence)
                    </span>
                </div>

                {peakPressureEvents.length === 0 ? (
                    <div style={styles.emptyState}>
                        <p style={styles.emptyTitle}>No promoted structural events detected</p>
                        <p style={styles.emptyReason}>
                            {/* MANDATORY: Explicit empty-state messaging (deterministic) */}
                            {stats.baselines_warm < stats.baselines_active ? (
                                <strong>Baselines warming up ({stats.baselines_ready || `${stats.baselines_warm} / ${stats.baselines_active}`} symbols ready)</strong>
                            ) : stats.condition_failures ? (
                                (() => {
                                    const failures = stats.condition_failures;
                                    const maxFailure = Object.entries(failures)
                                        .filter(([k]) => k !== 'baseline_not_warm')
                                        .sort(([, a], [, b]) => (b as number) - (a as number))[0];

                                    if (!maxFailure || maxFailure[1] === 0) {
                                        return 'No windows processed yet';
                                    }

                                    const [condition, count] = maxFailure;
                                    const messages: Record<string, string> = {
                                        'flow_surge': 'Flow surge absent (trade volume below P90 threshold)',
                                        'large_trade': 'Large trade participation absent',
                                        'compression': 'Compression/expansion absent (price not touching P95 bands)',
                                        'stress': 'External stress conditions not met (no liquidations or OI delta)'
                                    };

                                    return messages[condition] || stats.zero_reason || 'Awaiting multi-stream coincidence';
                                })()
                            ) : (
                                stats.zero_reason || 'Raw market activity may still be present'
                            )}
                        </p>
                        {stats.condition_failures && (
                            <div style={styles.failureBreakdown}>
                                <p style={styles.failureTitle}>Condition Failures:</p>
                                <ul style={styles.failureList}>
                                    {stats.condition_failures.baseline_not_warm > 0 && (
                                        <li>Baseline warming: {stats.condition_failures.baseline_not_warm}</li>
                                    )}
                                    {stats.condition_failures.flow_surge > 0 && (
                                        <li>Flow surge (P90): {stats.condition_failures.flow_surge}</li>
                                    )}
                                    {stats.condition_failures.large_trade > 0 && (
                                        <li>Large trade: {stats.condition_failures.large_trade}</li>
                                    )}
                                    {stats.condition_failures.compression > 0 && (
                                        <li>Compression/Expansion: {stats.condition_failures.compression}</li>
                                    )}
                                    {stats.condition_failures.stress > 0 && (
                                        <li>External stress: {stats.condition_failures.stress}</li>
                                    )}
                                </ul>
                            </div>
                        )}
                    </div>
                ) : (
                    <div style={styles.tableContainer}>
                        <table style={styles.table}>
                            <thead>
                                <tr style={styles.tableHeader}>
                                    <th style={styles.th}>Time</th>
                                    <th style={styles.th}>Symbol</th>
                                    <th style={styles.th}>Stress Sources</th>
                                    <th style={styles.th}>Flow</th>
                                    <th style={styles.th}>Kline</th>
                                    <th style={styles.th}>Liqs</th>
                                </tr>
                            </thead>
                            <tbody>
                                {peakPressureEvents.map((event, idx) => (
                                    <tr key={event.event_id} style={styles.ppRow}>
                                        <td style={styles.td}>{new Date(event.timestamp * 1000).toLocaleTimeString()}</td>
                                        <td style={styles.tdMono}>{event.symbol}</td>
                                        <td style={styles.tdStress}>{event.stress_sources.join(', ')}</td>
                                        <td style={styles.tdMono}>{event.metrics.abs_flow.toFixed(0)}</td>
                                        <td style={styles.tdMono}>
                                            {event.metrics.compressed ? 'Compressed' : event.metrics.expanded ? 'Expanded' : '-'}
                                        </td>
                                        <td style={styles.tdMono}>{event.metrics.liq_count}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* PANEL A: Raw Market Feed */}
            <div style={styles.panel}>
                <div
                    style={styles.collapsibleHeader}
                    onClick={() => setShowRawEvents(!showRawEvents)}
                >
                    <span style={styles.collapsibleTitle}>
                        {showRawEvents ? '▼' : '▶'} Raw Market Feed — No Interpretation
                    </span>
                    <span style={styles.collapsibleCount}>
                        {rawTrades.length} trades, {rawLiqs.length} liquidations
                    </span>
                </div>

                {showRawEvents && (
                    <div style={styles.rawContainer}>
                        {/* Raw Trades */}
                        <div style={styles.rawSection}>
                            <h4 style={styles.rawSectionTitle}>Trades</h4>
                            <div style={styles.rawTableContainer}>
                                <table style={styles.table}>
                                    <thead>
                                        <tr style={styles.tableHeader}>
                                            <th style={styles.thSmall}>Time</th>
                                            <th style={styles.thSmall}>Symbol</th>
                                            <th style={styles.thSmall}>Price</th>
                                            <th style={styles.thSmall}>Qty</th>
                                            <th style={styles.thSmall}>Side</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {rawTrades.slice(0, 50).map((trade, idx) => (
                                            <tr key={idx} style={styles.rawRow}>
                                                <td style={styles.tdSmall}>{new Date(trade.timestamp * 1000).toLocaleTimeString()}</td>
                                                <td style={styles.tdMonoSmall}>{trade.symbol}</td>
                                                <td style={styles.tdMonoSmall}>{trade.price.toFixed(2)}</td>
                                                <td style={styles.tdMonoSmall}>{trade.quantity.toFixed(3)}</td>
                                                <td style={{
                                                    ...styles.tdSmall,
                                                    color: trade.side === 'BUY' ? '#66cc66' : '#cc6666'
                                                }}>{trade.side}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        {/* Raw Liquidations */}
                        {rawLiqs.length > 0 && (
                            <div style={styles.rawSection}>
                                <h4 style={styles.rawSectionTitle}>Liquidations</h4>
                                <div style={styles.rawTableContainer}>
                                    <table style={styles.table}>
                                        <thead>
                                            <tr style={styles.tableHeader}>
                                                <th style={styles.thSmall}>Time</th>
                                                <th style={styles.thSmall}>Symbol</th>
                                                <th style={styles.thSmall}>Price</th>
                                                <th style={styles.thSmall}>Qty</th>
                                                <th style={styles.thSmall}>Side</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {rawLiqs.slice(0, 20).map((liq, idx) => (
                                                <tr key={idx} style={styles.liqRow}>
                                                    <td style={styles.tdSmall}>{new Date(liq.timestamp * 1000).toLocaleTimeString()}</td>
                                                    <td style={styles.tdMonoSmall}>{liq.symbol}</td>
                                                    <td style={styles.tdMonoSmall}>{liq.price.toFixed(2)}</td>
                                                    <td style={styles.tdMonoSmall}>{liq.quantity.toFixed(3)}</td>
                                                    <td style={{
                                                        ...styles.tdSmall,
                                                        color: liq.side === 'BUY' ? '#66cc66' : '#cc6666'
                                                    }}>{liq.side}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

const styles: Record<string, React.CSSProperties> = {
    container: {
        padding: '20px',
        backgroundColor: '#0a0a0a',
        minHeight: '100vh',
    },
    diagnostics: {
        display: 'flex',
        gap: '32px',
        padding: '16px',
        backgroundColor: '#1a1a1a',
        border: '1px solid #333',
        borderRadius: '4px',
        marginBottom: '20px',
    },
    diagItem: {
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
    },
    diagLabel: {
        color: '#888',
        fontSize: '12px',
        fontFamily: 'monospace',
    },
    diagValue: {
        color: '#e0e0e0',
        fontSize: '14px',
        fontWeight: 'bold',
        fontFamily: 'monospace',
    },
    panel: {
        marginBottom: '24px',
        border: '1px solid #333',
        borderRadius: '4px',
        overflow: 'hidden',
    },
    panelHeader: {
        padding: '16px',
        backgroundColor: '#1a1a1a',
        borderBottom: '1px solid #333',
    },
    panelTitle: {
        margin: 0,
        color: '#e0e0e0',
        fontSize: '16px',
        fontWeight: 'bold',
    },
    panelSubtitle: {
        color: '#666',
        fontSize: '12px',
        fontFamily: 'monospace',
    },
    emptyState: {
        padding: '60px 20px',
        textAlign: 'center',
        backgroundColor: '#0f0f0f',
    },
    emptyTitle: {
        color: '#888',
        fontSize: '14px',
        margin: '0 0 12px 0',
    },
    emptyReason: {
        color: '#666',
        fontSize: '12px',
        fontFamily: 'monospace',
        fontStyle: 'italic',
        margin: '0 0 24px 0',
    },
    failureBreakdown: {
        marginTop: '24px',
        padding: '16px',
        backgroundColor: '#1a1a1a',
        border: '1px solid #333',
        borderRadius: '4px',
        maxWidth: '500px',
        margin: '24px auto 0',
    },
    failureTitle: {
        color: '#aaa',
        fontSize: '12px',
        fontWeight: 'bold',
        margin: '0 0 8px 0',
    },
    failureList: {
        color: '#888',
        fontSize: '11px',
        fontFamily: 'monospace',
        margin: 0,
        paddingLeft: '20px',
        listStyle: 'disc',
    },
    tableContainer: {
        maxHeight: '400px',
        overflowY: 'auto',
    },
    rawTableContainer: {
        maxHeight: '300px',
        overflowY: 'auto',
    },
    table: {
        width: '100%',
        borderCollapse: 'collapse',
        fontSize: '12px',
        fontFamily: 'monospace',
    },
    tableHeader: {
        position: 'sticky',
        top: 0,
        backgroundColor: '#1a1a1a',
        zIndex: 10,
    },
    th: {
        padding: '10px 8px',
        textAlign: 'left',
        borderBottom: '2px solid #444',
        color: '#aaa',
        fontSize: '10px',
        textTransform: 'uppercase',
    },
    thSmall: {
        padding: '8px 6px',
        textAlign: 'left',
        borderBottom: '2px solid #444',
        color: '#888',
        fontSize: '9px',
        textTransform: 'uppercase',
    },
    ppRow: {
        borderBottom: '1px solid #333',
        backgroundColor: '#0f1a0f',
    },
    rawRow: {
        borderBottom: '1px solid #222',
    },
    liqRow: {
        borderBottom: '1px solid #222',
        backgroundColor: '#1a0f0f',
    },
    td: {
        padding: '10px 8px',
        color: '#ccc',
    },
    tdSmall: {
        padding: '6px',
        color: '#888',
        fontSize: '10px',
    },
    tdMono: {
        padding: '10px 8px',
        color: '#ccc',
        fontFamily: 'monospace',
        fontSize: '11px',
    },
    tdMonoSmall: {
        padding: '6px',
        color: '#888',
        fontFamily: 'monospace',
        fontSize: '10px',
    },
    tdStress: {
        padding: '10px 8px',
        color: '#cc8866',
        fontFamily: 'monospace',
        fontSize: '10px',
    },
    collapsibleHeader: {
        padding: '16px',
        backgroundColor: '#1a1a1a',
        cursor: 'pointer',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        userSelect: 'none',
    },
    collapsibleTitle: {
        color: '#e0e0e0',
        fontSize: '14px',
        fontWeight: 'bold',
    },
    collapsibleCount: {
        color: '#666',
        fontSize: '12px',
        fontFamily: 'monospace',
    },
    rawContainer: {
        padding: '16px',
        backgroundColor: '#0a0a0a',
    },
    rawSection: {
        marginBottom: '20px',
    },
    rawSectionTitle: {
        margin: '0 0 12px 0',
        color: '#888',
        fontSize: '12px',
        fontWeight: 'bold',
        textTransform: 'uppercase',
    },
};
