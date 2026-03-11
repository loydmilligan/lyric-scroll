/**
 * Lyric Scroll - Frontend Application
 */

class LyricScroll {
    constructor() {
        this.ws = null;
        this.lyrics = [];
        this.currentLineIndex = -1;
        this.state = 'idle'; // idle, playing, paused

        // Position interpolation
        this.lastPositionMs = 0;
        this.lastPositionTime = 0;  // Local timestamp when we received position
        this.animationFrameId = null;

        // DOM elements
        this.lyricsContent = document.getElementById('lyrics-content');
        this.statusMessage = document.getElementById('status-message');
        this.statusText = document.getElementById('status-text');
        this.trackTitle = document.getElementById('track-title');
        this.trackArtist = document.getElementById('track-artist');

        this.init();
    }

    init() {
        this.connect();
        this.setupEventListeners();
    }

    connect() {
        // Determine WebSocket URL
        // HA ingress proxies /api/hassio_ingress/xxx/* to addon's /*
        // So we just need to use relative path from current location
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

        // Try relative URL first (works with ingress proxy)
        let wsUrl;
        if (window.location.pathname.includes('hassio_ingress') || window.location.pathname.includes('/app/')) {
            // HA ingress - use relative path
            const basePath = window.location.pathname.replace(/\/$/, '');
            wsUrl = `${protocol}//${window.location.host}${basePath}/ws`;
        } else {
            // Direct access
            wsUrl = `${protocol}//${window.location.host}/ws`;
        }

        console.log('Lyric Scroll v0.2.1 - Connecting to WebSocket:', wsUrl);
        console.log('Location:', window.location.href);

        try {
            this.ws = new WebSocket(wsUrl);
        } catch (e) {
            console.error('WebSocket creation failed:', e);
            setTimeout(() => this.connect(), 3000);
            return;
        }

        this.ws.onopen = () => {
            console.log('WebSocket connected successfully');
        };

        this.ws.onmessage = (event) => {
            console.log('WebSocket message received');
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };

        this.ws.onclose = (event) => {
            console.log('WebSocket disconnected, code:', event.code, 'reason:', event.reason);
            setTimeout(() => this.connect(), 3000);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    handleMessage(message) {
        console.log('Received message:', message);

        switch (message.type) {
            case 'lyrics':
                this.handleLyrics(message.data);
                break;
            case 'position':
                this.handlePosition(message.data);
                break;
            case 'no_lyrics':
                this.handleNoLyrics(message.data);
                break;
            case 'loading':
                this.handleLoading(message.data);
                break;
            case 'idle':
                this.handleIdle();
                break;
        }
    }

    handleLoading(data) {
        this.lyrics = [];
        this.currentLineIndex = -1;
        this.lyricsContent.innerHTML = '';
        this.statusMessage.classList.remove('hidden');
        this.statusText.textContent = 'Loading lyrics...';

        if (data.track) {
            this.trackTitle.textContent = data.track.title || '-';
            this.trackArtist.textContent = data.track.artist || '-';
        }
    }

    handleLyrics(data) {
        // Stop any existing position tracking
        this.stopPositionTracking();
        this.currentLineIndex = -1;

        this.lyrics = data.lyrics || [];
        this.trackTitle.textContent = data.track?.title || '-';
        this.trackArtist.textContent = data.track?.artist || '-';

        console.log(`Loaded ${this.lyrics.length} lyrics lines`);

        this.statusMessage.classList.add('hidden');
        this.renderLyrics();
    }

    handlePosition(data) {
        const positionMs = data.position_ms;
        this.state = data.state;

        // Record position and local time for interpolation
        this.lastPositionMs = positionMs;
        this.lastPositionTime = performance.now();

        console.log(`Position update: ${(positionMs/1000).toFixed(1)}s, state: ${this.state}`);

        if (this.state === 'playing' && this.lyrics.length > 0) {
            this.startPositionTracking();
        } else {
            this.stopPositionTracking();
        }
    }

    startPositionTracking() {
        if (this.animationFrameId) return; // Already running

        const tick = () => {
            if (this.state !== 'playing') {
                this.stopPositionTracking();
                return;
            }

            // Interpolate position based on elapsed time
            const elapsed = performance.now() - this.lastPositionTime;
            const estimatedPosition = this.lastPositionMs + elapsed;

            this.updateCurrentLine(estimatedPosition);
            this.animationFrameId = requestAnimationFrame(tick);
        };

        this.animationFrameId = requestAnimationFrame(tick);
    }

    stopPositionTracking() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
            this.animationFrameId = null;
        }
    }

    handleNoLyrics(data) {
        this.lyrics = [];
        this.lyricsContent.innerHTML = '';
        this.statusMessage.classList.remove('hidden');
        this.statusText.textContent = 'No lyrics available';

        if (data.track) {
            this.trackTitle.textContent = data.track.title || '-';
            this.trackArtist.textContent = data.track.artist || '-';
        }
    }

    handleIdle() {
        this.stopPositionTracking();
        this.state = 'idle';
        this.lyrics = [];
        this.currentLineIndex = -1;
        this.lyricsContent.innerHTML = '';
        this.statusMessage.classList.remove('hidden');
        this.statusText.textContent = 'Waiting for music...';
        this.trackTitle.textContent = '-';
        this.trackArtist.textContent = '-';
    }

    renderLyrics() {
        this.lyricsContent.innerHTML = this.lyrics.map((line, index) =>
            `<div class="lyric-line" data-index="${index}">${this.escapeHtml(line.text)}</div>`
        ).join('');
    }

    updateCurrentLine(positionMs) {
        // Find the current line based on position
        let newIndex = -1;
        for (let i = this.lyrics.length - 1; i >= 0; i--) {
            if (this.lyrics[i].timestamp_ms <= positionMs) {
                newIndex = i;
                break;
            }
        }

        if (newIndex !== this.currentLineIndex) {
            this.currentLineIndex = newIndex;
            this.highlightCurrentLine();
        }
    }

    highlightCurrentLine() {
        const lines = this.lyricsContent.querySelectorAll('.lyric-line');

        lines.forEach((line, index) => {
            line.classList.remove('current', 'past');

            if (index === this.currentLineIndex) {
                line.classList.add('current');
                // Scroll current line into view
                line.scrollIntoView({ behavior: 'smooth', block: 'center' });
            } else if (index < this.currentLineIndex) {
                line.classList.add('past');
            }
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    setupEventListeners() {
        // Settings button (placeholder for now)
        document.getElementById('settings-btn').addEventListener('click', () => {
            console.log('Settings clicked - not yet implemented');
        });
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.lyricScroll = new LyricScroll();
});
