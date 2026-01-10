// Add this JavaScript to dashboard.html after the fetchEnhancedSignals function

// Live Positions Tracking
let livePositions = [];

function fetchLivePositions() {
    fetch('/api/live-positions')
        .then(r => r.json())
        .then(data => {
            if (data.positions) {
                livePositions = data.positions;
                renderLivePositions();
            }
        })
        .catch(err => console.error('Error fetching live positions:', err));
}

function renderLivePositions() {
    const container = document.getElementById('live-positions-container');
    if (!container) return;

    if (livePositions.length === 0) {
        container.innerHTML = `
            <div style="text-align: center; padding: 40px; color: #8b949e;">
                No active positions
            </div>
        `;
        return;
    }

    container.innerHTML = livePositions.map(pos => {
        const pnlColor = pos.unrealized_pnl >= 0 ? '#3fb950' : '#f85149';
        const pnlSign = pos.unrealized_pnl >= 0 ? '+' : '';
        const directionClass = pos.direction === 'LONG' ? 'long' : 'short';

        // Calculate duration
        const duration = Math.floor(pos.duration / 60); // minutes
        const durationStr = duration < 60 ? `${duration}m` : `${Math.floor(duration / 60)}h ${duration % 60}m`;

        // Progress to target/stop
        const targetProgress = Math.max(0, Math.min(100, 100 - Math.abs(pos.distance_to_target)));
        const stopProgress = Math.max(0, Math.min(100, 100 - Math.abs(pos.distance_to_stop)));

        return `
            <div class="position-card" style="background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div>
                        <span style="font-size: 18px; font-weight: 600;">${pos.symbol.replace('USDT', '')}</span>
                        <span class="signal-direction ${directionClass}" style="margin-left: 8px;">${pos.direction}</span>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 20px; font-weight: 600; color: ${pnlColor};">
                            ${pnlSign}${pos.unrealized_pnl.toFixed(2)}%
                        </div>
                        <div style="font-size: 11px; color: #8b949e;">${durationStr}</div>
                    </div>
                </div>
                
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 12px;">
                    <div>
                        <div style="font-size: 11px; color: #8b949e;">Entry</div>
                        <div style="font-size: 14px; color: #58a6ff;">$${pos.entry.toFixed(2)}</div>
                    </div>
                    <div>
                        <div style="font-size: 11px; color: #8b949e;">Current</div>
                        <div style="font-size: 14px; color: #c9d1d9;">$${pos.current.toFixed(2)}</div>
                    </div>
                    <div>
                        <div style="font-size: 11px; color: #8b949e;">Type</div>
                        <div style="font-size: 11px; color: #8b949e;">${pos.type}</div>
                    </div>
                </div>
                
                <div style="margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px;">
                        <span style="color: #8b949e;">To Target</span>
                        <span style="color: #3fb950;">$${pos.target.toFixed(2)} (${pos.distance_to_target.toFixed(1)}%)</span>
                    </div>
                    <div style="background: #21262d; height: 6px; border-radius: 3px; overflow: hidden;">
                        <div style="background: #3fb950; height: 100%; width: ${targetProgress}%; transition: width 0.3s;"></div>
                    </div>
                </div>
                
                <div>
                    <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px;">
                        <span style="color: #8b949e;">To Stop</span>
                        <span style="color: #f85149;">$${pos.stop.toFixed(2)} (${pos.distance_to_stop.toFixed(1)}%)</span>
                    </div>
                    <div style="background: #21262d; height: 6px; border-radius: 3px; overflow: hidden;">
                        <div style="background: #f85149; height: 100%; width: ${stopProgress}%; transition: width 0.3s;"></div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// Sound Notification
let lastSignalCount = 0;
let audioContext = null;

function playSignalSound() {
    try {
        // Create audio context if not exists
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }

        // Create oscillator for beep sound
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        // Configure sound (pleasant notification beep)
        oscillator.frequency.value = 800; // Hz
        oscillator.type = 'sine';

        gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);

        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.5);

        console.log('🔔 Signal notification sound played');
    } catch (err) {
        console.error('Error playing sound:', err);
    }
}

function checkForNewSignals() {
    fetch('/api/enhanced-signals')
        .then(r => r.json())
        .then(data => {
            const currentCount = (data.history || []).length;

            // Check if new signal appeared
            if (lastSignalCount > 0 && currentCount > lastSignalCount) {
                playSignalSound();

                // Show browser notification if permitted
                if ('Notification' in window && Notification.permission === 'granted') {
                    const latestSignal = data.history[0];
                    new Notification('🎯 New Trading Signal!', {
                        body: `${latestSignal.symbol} ${latestSignal.direction} - ${(latestSignal.confidence * 100).toFixed(0)}% confidence`,
                        icon: '/static/icon.png' // Add your icon path
                    });
                }
            }

            lastSignalCount = currentCount;
        })
        .catch(err => console.error('Error checking signals:', err));
}

// Request notification permission on page load
if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
}

// Update intervals
setInterval(fetchLivePositions, 2000); // Every 2 seconds
setInterval(checkForNewSignals, 5000); // Every 5 seconds

// Initial fetch
fetchLivePositions();
