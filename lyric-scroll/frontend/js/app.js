/**
 * Lyric Scroll - Frontend Application
 * Version: 0.3.0
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

        // Album art state
        this.albumArtUrl = null;
        this.albumArtState = 'hidden'; // hidden, fullscreen, side
        this.overlayTimeout = null;

        // DOM elements
        this.lyricsContent = document.getElementById('lyrics-content');
        this.statusMessage = document.getElementById('status-message');
        this.statusText = document.getElementById('status-text');
        this.trackTitle = document.getElementById('track-title');
        this.trackArtist = document.getElementById('track-artist');

        // Album art elements
        this.albumArtContainer = document.getElementById('album-art-container');
        this.albumArtImg = document.getElementById('album-art');

        // Track overlay elements
        this.trackOverlay = document.getElementById('track-overlay');

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

        console.log('Lyric Scroll v0.3.0 - Connecting to WebSocket:', wsUrl);
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

            // Show album art in fullscreen mode while loading
            if (data.track.album_art_url) {
                this.showAlbumArt(data.track.album_art_url, 'fullscreen');
            }

            // Show track overlay
            this.showTrackOverlay(data.track);
        }
    }

    handleLyrics(data) {
        // Stop any existing position tracking
        this.stopPositionTracking();
        this.currentLineIndex = -1;

        this.lyrics = data.lyrics || [];
        this.trackTitle.textContent = data.track?.title || '-';
        this.trackArtist.textContent = data.track?.artist || '-';

        console.log(`Loaded ${this.lyrics.length} lyrics lines, synced: ${data.synced}`);

        this.statusMessage.classList.add('hidden');

        // Handle album art
        if (data.track?.album_art_url) {
            this.albumArtUrl = data.track.album_art_url;
            // If lyrics are synced, we'll transition to side view when first line is sung
            // For unsynced lyrics, show side view immediately
            if (!data.synced || this.lyrics.length === 0) {
                this.showAlbumArt(this.albumArtUrl, 'side');
            }
            // else: keep fullscreen, will transition in updateCurrentLine
        }

        // Show track overlay
        if (data.track) {
            this.showTrackOverlay(data.track);
        }

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

            // Show album art fullscreen when no lyrics (nice visual)
            if (data.track.album_art_url) {
                this.showAlbumArt(data.track.album_art_url, 'fullscreen');
            }

            // Show track overlay
            this.showTrackOverlay(data.track);
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

        // Hide album art and track overlay
        this.hideAlbumArt();
        this.hideTrackOverlay();
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
            // Transition album art from fullscreen to side when first lyric starts
            if (newIndex >= 0 && this.currentLineIndex < 0 && this.albumArtState === 'fullscreen') {
                this.showAlbumArt(this.albumArtUrl, 'side');
            }

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

    // Album art display methods
    showAlbumArt(url, mode) {
        if (!url) {
            this.hideAlbumArt();
            return;
        }

        this.albumArtUrl = url;
        this.albumArtImg.src = url;
        this.albumArtContainer.classList.remove('hidden', 'fullscreen', 'side');
        this.albumArtContainer.classList.add(mode);
        this.albumArtState = mode;

        // Update body class for lyrics container adjustment
        if (mode === 'side') {
            document.body.classList.add('has-side-art');
        } else {
            document.body.classList.remove('has-side-art');
        }

        console.log(`Album art: ${mode}`);
    }

    hideAlbumArt() {
        this.albumArtContainer.classList.add('hidden');
        this.albumArtContainer.classList.remove('fullscreen', 'side');
        document.body.classList.remove('has-side-art');
        this.albumArtState = 'hidden';
        this.albumArtUrl = null;
    }

    // Track overlay (MTV style) methods
    showTrackOverlay(track) {
        if (!track) return;

        // Clear any existing timeout
        if (this.overlayTimeout) {
            clearTimeout(this.overlayTimeout);
        }

        // Populate overlay content
        const artistEl = this.trackOverlay.querySelector('.track-artist');
        const titleEl = this.trackOverlay.querySelector('.track-title');
        const albumEl = this.trackOverlay.querySelector('.track-album');

        artistEl.textContent = track.artist || '';
        titleEl.textContent = track.title || '';

        // Show album and year if available
        let albumText = track.album || '';
        if (track.year) {
            albumText += albumText ? ` (${track.year})` : track.year;
        }
        albumEl.textContent = albumText;

        // Show overlay
        this.trackOverlay.classList.remove('hidden', 'fade-out');

        // Auto-hide after 6 seconds
        this.overlayTimeout = setTimeout(() => {
            this.trackOverlay.classList.add('fade-out');
            // Remove completely after animation
            setTimeout(() => {
                this.trackOverlay.classList.add('hidden');
            }, 500);
        }, 6000);

        console.log('Track overlay shown');
    }

    hideTrackOverlay() {
        if (this.overlayTimeout) {
            clearTimeout(this.overlayTimeout);
            this.overlayTimeout = null;
        }
        this.trackOverlay.classList.add('hidden');
        this.trackOverlay.classList.remove('fade-out');
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
