/**
 * Live Status Header Component
 * 
 * Displays system mode, monitored symbols, timing, and throughput.
 * NO CONTROLS - display only.
 */

import React, { useEffect, useState } from 'react';
import { SystemStatus } from '../types/events';

const API_URL = 'http://localhost:8000';

export const LiveStatusHeader: React.FC = () => {
    const [status, setStatus] = useState<SystemStatus | null>(null);
    const [currentTime, setCurrentTime] = useState<number>(Date.now());

    // Fetch status periodically
    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const response = await fetch(`${API_URL}/api/status`);
                const data = await response.json();
                setStatus(data);
            } catch (error) {
                console.error('Failed to fetch status:', error);
            }
        };

        fetchStatus();
        const interval = setInterval(fetchStatus, 5000); // Update every 5s

        return () => clearInterval(interval);
    }, []);

    // Update current time every second
    useEffect(() => {
        const interval = setInterval(() => {
            setCurrentTime(Date.now());
        }, 1000);

        return () => clearInterval(interval);
    }, []);

    if (!status) {
        return (
            <header style={styles.header}>
                <div style={styles.statusItem}>
                    <span style={styles.label}>Loading...</span>
                </div>
            </header>
        );
    }

    const formatTime = (timestamp: number) => {
        return new Date(timestamp).toLocaleString();
    };

    const timeSinceActivity = status.last_activity
        ? Math.floor((currentTime - status.last_activity * 1000) / 1000)
        : null;

    return (
        <header style={styles.header}>
            <div style={styles.container}>
                <div style={styles.statusItem}>
                    <span style={styles.label}>Mode:</span>
                    <span style={styles.value}>{status.mode}</span>
                </div>

                <div style={styles.statusItem}>
                    <span style={styles.label}>Symbols:</span>
                    <span style={styles.value}>
                        {status.symbols.length > 0 ? status.symbols.join(', ') : 'None'}
                    </span>
                </div>

                <div style={styles.statusItem}>
                    <span style={styles.label}>Current Time:</span>
                    <span style={styles.value}>{formatTime(currentTime)}</span>
                </div>

                {status.last_activity > 0 && (
                    <div style={styles.statusItem}>
                        <span style={styles.label}>Last Activity:</span>
                        <span style={styles.value}>
                            {formatTime(status.last_activity * 1000)}
                            {timeSinceActivity !== null && ` (${timeSinceActivity}s ago)`}
                        </span>
                    </div>
                )}

                <div style={styles.statusItem}>
                    <span style={styles.label}>Event Rate:</span>
                    <span style={styles.value}>
                        {status.event_rate.toFixed(2)} events/min
                    </span>
                </div>

                <div style={styles.statusItem}>
                    <span style={styles.label}>Total Events:</span>
                    <span style={styles.value}>{status.event_count}</span>
                </div>
            </div>
        </header>
    );
};

const styles: Record<string, React.CSSProperties> = {
    header: {
        backgroundColor: '#1a1a1a',
        color: '#e0e0e0',
        padding: '16px',
        borderBottom: '1px solid #333',
        position: 'sticky',
        top: 0,
        zIndex: 100,
    },
    container: {
        display: 'flex',
        gap: '32px',
        flexWrap: 'wrap',
        maxWidth: '1600px',
        margin: '0 auto',
    },
    statusItem: {
        display: 'flex',
        flexDirection: 'column',
        gap: '4px',
    },
    label: {
        fontSize: '11px',
        textTransform: 'uppercase',
        color: '#888',
        letterSpacing: '0.5px',
    },
    value: {
        fontSize: '14px',
        fontWeight: 500,
        fontFamily: 'monospace',
    },
};
