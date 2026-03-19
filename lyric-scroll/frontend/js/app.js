/**
 * Lyric Scroll - Frontend Application
 * Version: 0.5.18
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
        this.lastServerUpdate = 0;  // Timestamp of last position update from server
        this.syncCheckInterval = null;  // Interval for checking sync health
        this.positionPollInterval = null;  // Interval for polling position

        // Album art state
        this.albumArtUrl = null;
        this.albumArtState = 'hidden'; // hidden, fullscreen, side
        this.overlayTimeout = null;

        // Settings (with defaults)
        this.settings = {
            theme: 'dark',
            offsetMs: 0,
            artPosition: 'left',  // left, right, hidden
            artSize: 'medium',    // small, medium, large, xlarge
            maPlayers: [],        // selected Music Assistant players
            maDefaultPlayer: '',  // default MA player
            maDisplayMappings: {}, // player -> display mappings
            autocastEnabled: false, // enable auto-casting
            autocastUrl: 'http://192.168.6.8:8099', // default cast URL
            displayIps: {},       // display entity_id -> IP address mapping
            castAppId: '',
            chromecastIp: '',
            castMethod: 'automation', // 'automation' or 'direct'
            neohabitEnabled: false,
            neohabitApiUrl: 'http://192.168.5.242:9000',
            neohabitUsername: '',
            neohabitPassword: '',
            neohabitProject: 'Billy Care',
            weatherApiKey: '',
            weatherZip: '',
            weatherUnits: 'imperial',
            fallbackUrls: [],
            fallbackRotationSeconds: 30
        };

        // Cast state
        this.castSender = null;

        // Timeline state
        this.songDurationMs = 0;
        this.isDraggingScrubber = false;
        this.timelineHideTimeout = null;

        // DOM elements
        this.lyricsContent = document.getElementById('lyrics-content');
        this.statusMessage = document.getElementById('status-message');
        this.statusText = document.getElementById('status-text');
        this.trackTitle = document.getElementById('track-title');
        this.trackArtist = document.getElementById('track-artist');

        // Timeline elements
        this.timelineContainer = document.getElementById('timeline-container');
        this.timelineScrubber = document.getElementById('timeline-scrubber');
        this.timelineProgress = document.getElementById('timeline-progress');
        this.timelineCurrent = document.getElementById('timeline-current');
        this.timelineDuration = document.getElementById('timeline-duration');

        // Album art elements
        this.albumArtContainer = document.getElementById('album-art-container');
        this.albumArtImg = document.getElementById('album-art');

        // Track overlay elements
        this.trackOverlay = document.getElementById('track-overlay');

        // Settings elements
        this.settingsPanel = document.getElementById('settings-panel');
        this.offsetSlider = document.getElementById('offset-slider');
        this.offsetValue = document.getElementById('offset-value');
        this.artPositionSelect = document.getElementById('art-position');
        this.artSizeSelect = document.getElementById('art-size');

        // Fallback screen elements
        this.neohabitEnabledCheckbox = document.getElementById('neohabit-enabled');
        this.neohabitApiUrlInput = document.getElementById('neohabit-api-url');
        this.neohabitUsernameInput = document.getElementById('neohabit-username');
        this.neohabitPasswordInput = document.getElementById('neohabit-password');
        this.neohabitProjectInput = document.getElementById('neohabit-project');
        this.weatherApiKeyInput = document.getElementById('weather-api-key');
        this.weatherZipInput = document.getElementById('weather-zip');
        this.weatherUnitsSelect = document.getElementById('weather-units');
        this.fallbackUrlsTextarea = document.getElementById('fallback-urls');
        this.fallbackRotationInput = document.getElementById('fallback-rotation');

        // Music Assistant elements
        this.maPlayersSelect = document.getElementById('ma-players');
        this.maDefaultPlayerSelect = document.getElementById('ma-default-player');
        this.maMappingList = document.getElementById('ma-mapping-list');
        this.autocastEnabledCheckbox = document.getElementById('autocast-enabled');
        this.autocastUrlInput = document.getElementById('autocast-url');
        this.displayIpsInput = document.getElementById('display-ips');
        this.castBtn = document.getElementById('cast-btn');
        this.castAppIdInput = document.getElementById('cast-app-id');
        this.chromecastIpInput = document.getElementById('chromecast-ip');
        this.castMethodSelect = document.getElementById('cast-method');

        // MA data
        this.maPlayers = [];
        this.maDisplays = [];

        this.init();
    }

    init() {
        this.loadSettings();
        this.applySettings();
        this.connect();
        this.setupEventListeners();
    }

    loadSettings() {
        try {
            const saved = localStorage.getItem('lyricScrollSettings');
            if (saved) {
                const parsed = JSON.parse(saved);
                this.settings = { ...this.settings, ...parsed };
                console.log('Settings loaded:', this.settings);
            }
        } catch (e) {
            console.error('Failed to load settings:', e);
        }
    }

    saveSettings() {
        try {
            localStorage.setItem('lyricScrollSettings', JSON.stringify(this.settings));
            console.log('Settings saved:', this.settings);
        } catch (e) {
            console.error('Failed to save settings:', e);
        }
    }

    applySettings() {
        // Apply theme
        this.setTheme(this.settings.theme);

        // Apply offset slider value
        if (this.offsetSlider) {
            this.offsetSlider.value = this.settings.offsetMs;
            this.offsetValue.textContent = `${this.settings.offsetMs}ms`;
        }

        // Apply art position
        if (this.artPositionSelect) {
            this.artPositionSelect.value = this.settings.artPosition;
        }
        this.applyArtPosition();

        // Apply art size
        if (this.artSizeSelect) {
            this.artSizeSelect.value = this.settings.artSize;
        }
        this.applyArtSize();

        // Update theme button active state
        this.updateThemeButtons();
    }

    setTheme(theme) {
        document.body.classList.remove('theme-dark', 'theme-light', 'theme-oled');
        if (theme !== 'dark') {
            document.body.classList.add(`theme-${theme}`);
        }
        this.settings.theme = theme;
        this.updateThemeButtons();
    }

    updateThemeButtons() {
        document.querySelectorAll('.theme-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.theme === this.settings.theme);
        });
    }

    applyArtPosition() {
        const position = this.settings.artPosition;
        this.albumArtContainer.classList.remove('art-right');
        document.body.classList.remove('art-right');

        if (position === 'right') {
            this.albumArtContainer.classList.add('art-right');
            document.body.classList.add('art-right');
        } else if (position === 'hidden') {
            // Will be handled in showAlbumArt
        }
    }

    applyArtSize() {
        const size = this.settings.artSize;
        // Remove all size classes
        this.albumArtContainer.classList.remove('art-small', 'art-medium', 'art-large', 'art-xlarge');
        document.body.classList.remove('art-small', 'art-medium', 'art-large', 'art-xlarge');

        // Add current size class
        this.albumArtContainer.classList.add(`art-${size}`);
        document.body.classList.add(`art-${size}`);
    }

    async openSettings() {
        this.settingsPanel.classList.remove('hidden');
        // Fetch MA data when settings are opened
        await this.fetchMAData();
    }

    closeSettings() {
        this.settingsPanel.classList.add('hidden');
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

        console.log('Lyric Scroll v0.5.20 - Connecting to WebSocket:', wsUrl);
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
        this.lastPositionMs = 0;
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
        // Check if this is the same track
        const isSameTrack = this.currentTrack &&
            this.currentTrack.title === data.track?.title &&
            this.currentTrack.artist === data.track?.artist;

        // Only reset position for NEW tracks
        if (!isSameTrack) {
            this.stopPositionTracking();
            this.currentLineIndex = -1;
            this.lastPositionMs = 0;
            this.lastPositionTime = 0;
        }

        // Update current track reference
        this.currentTrack = data.track;

        this.lyrics = data.lyrics || [];
        this.trackTitle.textContent = data.track?.title || '-';
        this.trackArtist.textContent = data.track?.artist || '-';

        console.log(`Loaded ${this.lyrics.length} lyrics lines, synced: ${data.synced}`);

        this.statusMessage.classList.add('hidden');
        this.showVisualizer(false);

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
        this.lastServerUpdate = performance.now();

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
            this.updateTimeline(estimatedPosition);
            this.animationFrameId = requestAnimationFrame(tick);
        };

        this.animationFrameId = requestAnimationFrame(tick);

        // Clear any existing interval
        if (this.syncCheckInterval) clearInterval(this.syncCheckInterval);
        // Sync health check disabled - MA players don't report media_position
        // Just trust the initial sync and let lyrics play
        // this.syncCheckInterval = setInterval(() => this.checkSyncHealth(), 3000);
    }

    stopPositionTracking() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
            this.animationFrameId = null;
        }
        if (this.syncCheckInterval) {
            clearInterval(this.syncCheckInterval);
            this.syncCheckInterval = null;
        }
    }

    async pollPosition() {
        // Request current position from server via fetch
        try {
            const response = await fetch('/api/position');
            if (response.ok) {
                const data = await response.json();
                if (data.position_ms !== undefined) {
                    console.log('Position poll response:', data.position_ms);

                    // Calculate current estimated position
                    const elapsed = performance.now() - this.lastPositionTime;
                    const estimatedPosition = this.lastPositionMs + elapsed;

                    // Don't accept poll if it would jump backwards more than 5 seconds
                    // (unless we're near the start of the song)
                    const jumpBackMs = estimatedPosition - data.position_ms;
                    if (jumpBackMs > 5000 && data.position_ms > 2000) {
                        console.warn(`Ignoring poll - would jump back ${(jumpBackMs/1000).toFixed(1)}s`);
                        return;
                    }

                    this.lastPositionMs = data.position_ms;
                    this.lastPositionTime = performance.now();
                    this.lastServerUpdate = performance.now();
                }
            }
        } catch (err) {
            console.error('Position poll failed:', err);
        }
    }

    checkSyncHealth() {
        const timeSinceUpdate = performance.now() - this.lastServerUpdate;

        // If no update in 5 seconds and we're supposed to be playing, poll
        if (this.state === 'playing' && timeSinceUpdate > 5000) {
            console.warn('No position update in 5s, polling...');
            this.pollPosition();
        }
    }

    handleNoLyrics(data) {
        this.lyrics = [];
        this.lyricsContent.innerHTML = '';
        this.statusMessage.classList.remove('hidden');
        this.statusText.textContent = 'No lyrics available';

        // Show visualizer when no lyrics
        this.showVisualizer(true);

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
        this.lastPositionMs = 0;
        this.lyricsContent.innerHTML = '';
        this.statusMessage.classList.remove('hidden');
        this.statusText.textContent = 'Waiting for music...';
        this.trackTitle.textContent = '-';
        this.trackArtist.textContent = '-';

        // Clear sync check interval
        if (this.syncCheckInterval) {
            clearInterval(this.syncCheckInterval);
            this.syncCheckInterval = null;
        }

        // Hide album art, track overlay, visualizer, and timeline
        this.hideAlbumArt();
        this.hideTrackOverlay();
        this.showVisualizer(false);
        this.hideTimeline();
    }

    renderLyrics() {
        this.lyricsContent.innerHTML = this.lyrics.map((line, index) =>
            `<div class="lyric-line" data-index="${index}">${this.escapeHtml(line.text)}</div>`
        ).join('');

        // Calculate song duration from last lyric timestamp
        if (this.lyrics.length > 0) {
            const lastLyric = this.lyrics[this.lyrics.length - 1];
            // Add 5 seconds buffer after last lyric
            this.songDurationMs = lastLyric.timestamp_ms + 5000;
            this.showTimeline(this.songDurationMs);
        }
    }

    updateCurrentLine(positionMs) {
        // Apply offset setting (positive = lyrics appear later, negative = earlier)
        const adjustedPosition = positionMs + this.settings.offsetMs;

        // Safety check: if position seems invalid or very high for song start, ignore
        // This prevents jumping to the end due to stale position data
        if (this.lyrics.length === 0) {
            return;
        }

        // If first lyric hasn't started yet, stay at index -1
        const firstLyricTime = this.lyrics[0]?.timestamp_ms || 0;
        if (adjustedPosition < firstLyricTime) {
            if (this.currentLineIndex !== -1) {
                this.currentLineIndex = -1;
                this.highlightCurrentLine();
            }
            return;
        }

        // Find the current line based on adjusted position
        let newIndex = -1;
        for (let i = this.lyrics.length - 1; i >= 0; i--) {
            if (this.lyrics[i].timestamp_ms <= adjustedPosition) {
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
        if (!url || this.settings.artPosition === 'hidden') {
            this.hideAlbumArt();
            return;
        }

        this.albumArtUrl = url;
        this.albumArtImg.src = url;
        this.albumArtContainer.classList.remove('hidden', 'fullscreen', 'side');
        this.albumArtContainer.classList.add(mode);
        this.albumArtState = mode;

        // Apply position and size settings
        this.applyArtPosition();
        this.applyArtSize();

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

    // Visualizer for no-lyrics mode
    showVisualizer(show) {
        const visualizer = document.getElementById('visualizer');
        if (visualizer) {
            if (show) {
                visualizer.classList.remove('hidden');
            } else {
                visualizer.classList.add('hidden');
            }
        }
    }

    // Timeline scrubber methods
    updateTimeline(positionMs) {
        if (!this.timelineContainer || !this.songDurationMs) return;

        const progress = Math.min(100, (positionMs / this.songDurationMs) * 100);

        if (!this.isDraggingScrubber) {
            this.timelineScrubber.value = progress;
            this.timelineProgress.style.width = progress + '%';
        }

        this.timelineCurrent.textContent = this.formatTime(positionMs);
    }

    formatTime(ms) {
        const seconds = Math.floor(ms / 1000);
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return mins + ':' + secs.toString().padStart(2, '0');
    }

    showTimeline(durationMs) {
        if (!this.timelineContainer) return;

        this.songDurationMs = durationMs;
        this.timelineDuration.textContent = this.formatTime(durationMs);
        this.timelineContainer.classList.remove('hidden');

        // Auto-hide after 3 seconds of no interaction
        this.scheduleTimelineHide();
    }

    hideTimeline() {
        if (this.timelineContainer) {
            this.timelineContainer.classList.add('hidden');
        }
    }

    scheduleTimelineHide() {
        if (this.timelineHideTimeout) clearTimeout(this.timelineHideTimeout);
        this.timelineHideTimeout = setTimeout(() => {
            if (!this.isDraggingScrubber) {
                this.timelineContainer.classList.remove('visible');
            }
        }, 3000);
    }

    initCast() {
        // Button is always visible, but mark as unavailable if no app ID
        if (!this.settings.castAppId) {
            console.log('No Cast App ID configured');
            if (this.castBtn) {
                this.updateCastUI('unavailable', 'Cast App ID required');
            }
            return;
        }

        // Check if Cast SDK is available (only works in Chrome)
        if (typeof cast === 'undefined' || typeof chrome === 'undefined' || !chrome.cast) {
            console.log('Cast SDK not available (not Chrome or extension disabled)');
            if (this.castBtn) {
                this.updateCastUI('unavailable', 'Cast SDK not available');
            }
            return;
        }

        try {
            this.castSender = new LyricScrollCastSender(this.settings.castAppId);

            this.castSender.onStatusChange = (state, message) => {
                this.updateCastUI(state, message);

                // Auto-cast lyrics URL when connected
                if (state === 'connected') {
                    this.castCurrentLyrics();
                }
            };

            // Update UI with ready state
            this.updateCastUI('ready', 'Cast to Chromecast');
        } catch (err) {
            console.error('Failed to initialize Cast:', err);
            if (this.castBtn) {
                this.updateCastUI('error', 'Cast initialization failed');
            }
        }
    }

    updateCastUI(state, message) {
        if (!this.castBtn) return;

        this.castBtn.dataset.state = state;
        this.castBtn.title = message;  // Show status in tooltip

        // Update classes
        this.castBtn.classList.remove('connected', 'unavailable');
        if (state === 'connected') {
            this.castBtn.classList.add('connected');
        } else if (state === 'unavailable' || state === 'error') {
            this.castBtn.classList.add('unavailable');
        }
    }

    async castCurrentLyrics() {
        if (!this.castSender?.isConnected()) return;

        // Build the URL to cast - use the autocast URL (which should be the addon's LAN IP)
        const lyricsUrl = this.settings.autocastUrl || window.location.origin;

        try {
            await this.castSender.castUrl(lyricsUrl);
            console.log('Cast lyrics URL:', lyricsUrl);
        } catch (err) {
            console.error('Failed to cast URL:', err);
        }
    }

    // Music Assistant API methods
    async fetchMAData() {
        try {
            // Fetch players, displays, and settings in parallel
            const [playersRes, displaysRes, settingsRes] = await Promise.all([
                fetch('/api/ma/players'),
                fetch('/api/ma/displays'),
                fetch('/api/settings')
            ]);

            if (playersRes.ok) {
                const data = await playersRes.json();
                this.maPlayers = data.players || [];
                this.populateMAPlayers();
            }

            if (displaysRes.ok) {
                const data = await displaysRes.json();
                this.maDisplays = data.displays || [];
            }

            if (settingsRes.ok) {
                const serverSettings = await settingsRes.json();
                // Merge server settings with local settings (server uses snake_case)
                if (serverSettings.ma_players) {
                    this.settings.maPlayers = serverSettings.ma_players;
                }
                if (serverSettings.default_player) {
                    this.settings.maDefaultPlayer = serverSettings.default_player;
                }
                if (serverSettings.display_mappings) {
                    this.settings.maDisplayMappings = serverSettings.display_mappings;
                }
                if (serverSettings.autocast_enabled !== undefined) {
                    this.settings.autocastEnabled = serverSettings.autocast_enabled;
                }
                if (serverSettings.autocast_url) {
                    this.settings.autocastUrl = serverSettings.autocast_url;
                }
                if (serverSettings.display_ips) {
                    this.settings.displayIps = serverSettings.display_ips;
                }
                if (serverSettings.cast_app_id) {
                    this.settings.castAppId = serverSettings.cast_app_id;
                }
                if (serverSettings.chromecast_ip) {
                    this.settings.chromecastIp = serverSettings.chromecast_ip;
                }
                if (serverSettings.cast_method) {
                    this.settings.castMethod = serverSettings.cast_method;
                }
                if (serverSettings.neohabit_enabled !== undefined) {
                    this.settings.neohabitEnabled = serverSettings.neohabit_enabled;
                }
                if (serverSettings.neohabit_api_url !== undefined) {
                    this.settings.neohabitApiUrl = serverSettings.neohabit_api_url;
                }
                if (serverSettings.neohabit_username !== undefined) {
                    this.settings.neohabitUsername = serverSettings.neohabit_username;
                }
                if (serverSettings.neohabit_password !== undefined) {
                    this.settings.neohabitPassword = serverSettings.neohabit_password;
                }
                if (serverSettings.neohabit_project_name !== undefined) {
                    this.settings.neohabitProject = serverSettings.neohabit_project_name;
                }
                if (serverSettings.weather_api_key !== undefined) {
                    this.settings.weatherApiKey = serverSettings.weather_api_key;
                }
                if (serverSettings.weather_zip !== undefined) {
                    this.settings.weatherZip = serverSettings.weather_zip;
                }
                if (serverSettings.weather_units !== undefined) {
                    this.settings.weatherUnits = serverSettings.weather_units;
                }
                if (serverSettings.fallback_urls !== undefined) {
                    this.settings.fallbackUrls = serverSettings.fallback_urls;
                }
                if (serverSettings.fallback_rotation_seconds !== undefined) {
                    this.settings.fallbackRotationSeconds = serverSettings.fallback_rotation_seconds;
                }
                this.updateMAUI();
                this.initCast();
            }
        } catch (e) {
            console.error('Failed to fetch MA data:', e);
        }
    }

    populateMAPlayers() {
        this.maPlayersSelect.innerHTML = '';

        if (this.maPlayers.length === 0) {
            this.maPlayersSelect.innerHTML = '<option disabled>No players available</option>';
            return;
        }

        this.maPlayers.forEach(player => {
            const option = document.createElement('option');
            option.value = player.entity_id;
            option.textContent = player.friendly_name || player.entity_id;
            if (this.settings.maPlayers.includes(player.entity_id)) {
                option.selected = true;
            }
            this.maPlayersSelect.appendChild(option);
        });

        // Update default player dropdown
        this.updateDefaultPlayerOptions();
    }

    updateDefaultPlayerOptions() {
        this.maDefaultPlayerSelect.innerHTML = '<option value="">None</option>';

        const selectedPlayers = Array.from(this.maPlayersSelect.selectedOptions).map(opt => opt.value);

        selectedPlayers.forEach(playerId => {
            const player = this.maPlayers.find(p => p.entity_id === playerId);
            if (player) {
                const option = document.createElement('option');
                option.value = player.entity_id;
                option.textContent = player.friendly_name || player.entity_id;
                if (this.settings.maDefaultPlayer === player.entity_id) {
                    option.selected = true;
                }
                this.maDefaultPlayerSelect.appendChild(option);
            }
        });
    }

    updateMAUI() {
        // Update selected players
        if (this.maPlayersSelect) {
            Array.from(this.maPlayersSelect.options).forEach(option => {
                option.selected = this.settings.maPlayers.includes(option.value);
            });
        }

        // Rebuild default player dropdown with current selections
        this.updateDefaultPlayerOptions();

        // Update default player
        if (this.maDefaultPlayerSelect) {
            this.maDefaultPlayerSelect.value = this.settings.maDefaultPlayer;
        }

        // Update display mappings
        this.renderDisplayMappings();

        // Update autocast settings
        if (this.autocastEnabledCheckbox) {
            this.autocastEnabledCheckbox.checked = this.settings.autocastEnabled;
        }
        if (this.autocastUrlInput) {
            this.autocastUrlInput.value = this.settings.autocastUrl;
        }
        if (this.displayIpsInput) {
            this.displayIpsInput.value = JSON.stringify(this.settings.displayIps);
        }

        // Update Cast App ID
        if (this.castAppIdInput) {
            this.castAppIdInput.value = this.settings.castAppId || '';
        }

        // Update Chromecast IP
        if (this.chromecastIpInput) {
            this.chromecastIpInput.value = this.settings.chromecastIp || '';
        }

        // Update Cast Method
        if (this.castMethodSelect) {
            this.castMethodSelect.value = this.settings.castMethod || 'automation';
        }

        // Update Neohabit settings
        if (this.neohabitEnabledCheckbox) {
            this.neohabitEnabledCheckbox.checked = this.settings.neohabitEnabled || false;
        }
        if (this.neohabitApiUrlInput) {
            this.neohabitApiUrlInput.value = this.settings.neohabitApiUrl || 'http://192.168.5.242:9000';
        }
        if (this.neohabitUsernameInput) {
            this.neohabitUsernameInput.value = this.settings.neohabitUsername || '';
        }
        if (this.neohabitPasswordInput) {
            this.neohabitPasswordInput.value = this.settings.neohabitPassword || '';
        }
        if (this.neohabitProjectInput) {
            this.neohabitProjectInput.value = this.settings.neohabitProject || 'Billy Care';
        }

        // Update Fallback Screen settings
        if (this.weatherApiKeyInput) {
            this.weatherApiKeyInput.value = this.settings.weatherApiKey || '';
        }
        if (this.weatherZipInput) {
            this.weatherZipInput.value = this.settings.weatherZip || '';
        }
        if (this.weatherUnitsSelect) {
            this.weatherUnitsSelect.value = this.settings.weatherUnits || 'imperial';
        }
        if (this.fallbackUrlsTextarea) {
            this.fallbackUrlsTextarea.value = (this.settings.fallbackUrls || []).join('\n');
        }
        if (this.fallbackRotationInput) {
            this.fallbackRotationInput.value = this.settings.fallbackRotationSeconds || 30;
        }
    }

    renderDisplayMappings() {
        if (!this.maMappingList) return;

        this.maMappingList.innerHTML = '';

        const selectedPlayers = Array.from(this.maPlayersSelect.selectedOptions).map(opt => opt.value);

        if (selectedPlayers.length === 0) {
            this.maMappingList.innerHTML = '<p class="settings-hint">Select players to configure display mappings</p>';
            return;
        }

        selectedPlayers.forEach(playerId => {
            const player = this.maPlayers.find(p => p.entity_id === playerId);
            if (!player) return;

            const mappingDiv = document.createElement('div');
            mappingDiv.className = 'mapping-item';

            // Speaker icon
            const speakerIcon = document.createElement('span');
            speakerIcon.className = 'mapping-icon';
            speakerIcon.textContent = '🔊';
            speakerIcon.title = 'Music Player';

            // Player name
            const playerName = document.createElement('span');
            playerName.className = 'mapping-player-name';
            playerName.textContent = player.friendly_name || player.entity_id;

            // Arrow
            const arrow = document.createElement('span');
            arrow.className = 'mapping-arrow';
            arrow.textContent = '→';

            // Display select
            const select = document.createElement('select');
            select.className = 'ma-display-select mapping-select';
            select.dataset.playerId = playerId;

            // Add "None" option
            const noneOption = document.createElement('option');
            noneOption.value = '';
            noneOption.textContent = 'No display';
            select.appendChild(noneOption);

            // Add display options
            this.maDisplays.forEach(display => {
                const option = document.createElement('option');
                option.value = display.entity_id;
                option.textContent = display.friendly_name || display.entity_id;
                if (this.settings.maDisplayMappings[playerId] === display.entity_id) {
                    option.selected = true;
                }
                select.appendChild(option);
            });

            // Display/lyrics icon
            const displayIcon = document.createElement('span');
            displayIcon.className = 'mapping-display-icon';
            displayIcon.textContent = '📺';
            displayIcon.title = 'Lyrics Display';

            // Add change listener
            select.addEventListener('change', (e) => {
                this.settings.maDisplayMappings[playerId] = e.target.value;
                this.saveMASettings();
            });

            mappingDiv.appendChild(speakerIcon);
            mappingDiv.appendChild(playerName);
            mappingDiv.appendChild(arrow);
            mappingDiv.appendChild(select);
            mappingDiv.appendChild(displayIcon);
            this.maMappingList.appendChild(mappingDiv);
        });
    }

    async saveMASettings() {
        try {
            const response = await fetch('/api/settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    ma_players: this.settings.maPlayers,
                    default_player: this.settings.maDefaultPlayer,
                    display_mappings: this.settings.maDisplayMappings,
                    autocast_enabled: this.settings.autocastEnabled,
                    autocast_url: this.settings.autocastUrl,
                    display_ips: this.settings.displayIps,
                    cast_app_id: this.settings.castAppId,
                    chromecast_ip: this.settings.chromecastIp,
                    cast_method: this.settings.castMethod,
                    neohabit_enabled: this.settings.neohabitEnabled,
                    neohabit_api_url: this.settings.neohabitApiUrl,
                    neohabit_username: this.settings.neohabitUsername,
                    neohabit_password: this.settings.neohabitPassword,
                    neohabit_project_name: this.settings.neohabitProject,
                    weather_api_key: this.settings.weatherApiKey,
                    weather_zip: this.settings.weatherZip,
                    weather_units: this.settings.weatherUnits,
                    fallback_urls: this.settings.fallbackUrls,
                    fallback_rotation_seconds: this.settings.fallbackRotationSeconds
                })
            });

            if (!response.ok) {
                console.error('Failed to save MA settings');
            } else {
                console.log('MA settings saved:', this.settings);
            }
        } catch (e) {
            console.error('Failed to save MA settings:', e);
        }
    }

    setupEventListeners() {
        // Settings button - open panel
        document.getElementById('settings-btn').addEventListener('click', () => {
            this.openSettings();
        });

        // Settings close button
        document.getElementById('settings-close').addEventListener('click', () => {
            this.closeSettings();
        });

        // Close settings when clicking outside (on the main content)
        document.getElementById('lyrics-container').addEventListener('click', () => {
            if (!this.settingsPanel.classList.contains('hidden')) {
                this.closeSettings();
            }
        });

        // Theme buttons
        document.querySelectorAll('.theme-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.setTheme(btn.dataset.theme);
                this.saveSettings();
            });
        });

        // Offset slider
        this.offsetSlider.addEventListener('input', (e) => {
            const value = parseInt(e.target.value, 10);
            this.settings.offsetMs = value;
            this.offsetValue.textContent = `${value}ms`;
        });

        this.offsetSlider.addEventListener('change', () => {
            this.saveSettings();
        });

        // Album art position
        this.artPositionSelect.addEventListener('change', (e) => {
            this.settings.artPosition = e.target.value;
            this.applyArtPosition();

            // If changing to hidden while art is showing, hide it
            if (e.target.value === 'hidden' && this.albumArtState !== 'hidden') {
                this.hideAlbumArt();
            }
            // If changing from hidden to visible, show art if we have a URL
            else if (e.target.value !== 'hidden' && this.albumArtUrl && this.albumArtState === 'hidden') {
                this.showAlbumArt(this.albumArtUrl, 'side');
            }

            this.saveSettings();
        });

        // Album art size
        this.artSizeSelect.addEventListener('change', (e) => {
            this.settings.artSize = e.target.value;
            this.applyArtSize();
            this.saveSettings();
        });

        // Keyboard shortcut to close settings (Escape)
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !this.settingsPanel.classList.contains('hidden')) {
                this.closeSettings();
            }
        });

        // Music Assistant - Players selection
        if (this.maPlayersSelect) {
            this.maPlayersSelect.addEventListener('change', () => {
                const selectedPlayers = Array.from(this.maPlayersSelect.selectedOptions).map(opt => opt.value);
                this.settings.maPlayers = selectedPlayers;

                // Update default player options
                this.updateDefaultPlayerOptions();

                // Re-render display mappings
                this.renderDisplayMappings();

                this.saveMASettings();
            });
        }

        // Music Assistant - Default player selection
        if (this.maDefaultPlayerSelect) {
            this.maDefaultPlayerSelect.addEventListener('change', (e) => {
                this.settings.maDefaultPlayer = e.target.value;
                this.saveMASettings();
            });
        }

        // Autocast - Enable/disable
        if (this.autocastEnabledCheckbox) {
            this.autocastEnabledCheckbox.addEventListener('change', (e) => {
                this.settings.autocastEnabled = e.target.checked;
                this.saveMASettings();
            });
        }

        // Autocast - URL
        if (this.autocastUrlInput) {
            this.autocastUrlInput.addEventListener('change', (e) => {
                this.settings.autocastUrl = e.target.value;
                this.saveMASettings();
            });
        }

        // Display IPs
        if (this.displayIpsInput) {
            this.displayIpsInput.addEventListener('change', (e) => {
                try {
                    this.settings.displayIps = JSON.parse(e.target.value);
                    this.saveMASettings();
                } catch (error) {
                    console.error('Invalid JSON for display IPs:', error);
                }
            });
        }

        // Cast button click
        if (this.castBtn) {
            this.castBtn.addEventListener('click', () => {
                if (!this.castSender) return;
                if (this.castSender.isConnected()) {
                    this.castSender.stopCasting();
                } else {
                    this.castSender.startCasting();
                }
            });
        }

        // Cast App ID input
        if (this.castAppIdInput) {
            this.castAppIdInput.addEventListener('change', (e) => {
                this.settings.castAppId = e.target.value.trim().toUpperCase();
                this.saveSettings();
                this.saveMASettings();
                // Re-initialize cast with new app ID
                if (this.settings.castAppId) {
                    this.initCast();
                }
            });
        }

        // Chromecast IP input
        if (this.chromecastIpInput) {
            this.chromecastIpInput.addEventListener('change', (e) => {
                this.settings.chromecastIp = e.target.value.trim();
                this.saveSettings();
                this.saveMASettings();
            });
        }

        // Cast Method select
        if (this.castMethodSelect) {
            this.castMethodSelect.addEventListener('change', (e) => {
                this.settings.castMethod = e.target.value;
                this.saveSettings();
                this.saveMASettings();
            });
        }

        // Neohabit - Enable checkbox
        if (this.neohabitEnabledCheckbox) {
            this.neohabitEnabledCheckbox.addEventListener('change', (e) => {
                this.settings.neohabitEnabled = e.target.checked;
                this.saveMASettings();
            });
        }

        // Neohabit - API URL
        if (this.neohabitApiUrlInput) {
            this.neohabitApiUrlInput.addEventListener('change', (e) => {
                this.settings.neohabitApiUrl = e.target.value.trim();
                this.saveMASettings();
            });
        }

        // Neohabit - Username
        if (this.neohabitUsernameInput) {
            this.neohabitUsernameInput.addEventListener('change', (e) => {
                this.settings.neohabitUsername = e.target.value.trim();
                this.saveMASettings();
            });
        }

        // Neohabit - Password
        if (this.neohabitPasswordInput) {
            this.neohabitPasswordInput.addEventListener('change', (e) => {
                this.settings.neohabitPassword = e.target.value.trim();
                this.saveMASettings();
            });
        }

        // Neohabit - Project Name
        if (this.neohabitProjectInput) {
            this.neohabitProjectInput.addEventListener('change', (e) => {
                this.settings.neohabitProject = e.target.value.trim();
                this.saveMASettings();
            });
        }

        // Fallback Screen - Weather API Key
        if (this.weatherApiKeyInput) {
            this.weatherApiKeyInput.addEventListener('change', (e) => {
                this.settings.weatherApiKey = e.target.value.trim();
                this.saveMASettings();
            });
        }

        // Fallback Screen - Weather ZIP
        if (this.weatherZipInput) {
            this.weatherZipInput.addEventListener('change', (e) => {
                this.settings.weatherZip = e.target.value.trim();
                this.saveMASettings();
            });
        }

        // Fallback Screen - Weather Units
        if (this.weatherUnitsSelect) {
            this.weatherUnitsSelect.addEventListener('change', (e) => {
                this.settings.weatherUnits = e.target.value;
                this.saveMASettings();
            });
        }

        // Fallback Screen - URLs
        if (this.fallbackUrlsTextarea) {
            this.fallbackUrlsTextarea.addEventListener('change', (e) => {
                // Split by newlines, trim, and filter out empty lines
                this.settings.fallbackUrls = e.target.value
                    .split('\n')
                    .map(url => url.trim())
                    .filter(url => url.length > 0);
                this.saveMASettings();
            });
        }

        // Fallback Screen - Rotation Seconds
        if (this.fallbackRotationInput) {
            this.fallbackRotationInput.addEventListener('change', (e) => {
                this.settings.fallbackRotationSeconds = parseInt(e.target.value, 10) || 30;
                this.saveMASettings();
            });
        }

        // Timeline scrubber event listeners
        if (this.timelineScrubber) {
            this.timelineScrubber.addEventListener('input', (e) => {
                this.isDraggingScrubber = true;
                const progress = e.target.value / 100;
                const newPosition = progress * this.songDurationMs;
                this.timelineProgress.style.width = e.target.value + '%';
                this.timelineCurrent.textContent = this.formatTime(newPosition);
            });

            this.timelineScrubber.addEventListener('change', (e) => {
                const progress = e.target.value / 100;
                const newPosition = progress * this.songDurationMs;
                // Update lyrics position
                this.lastPositionMs = newPosition;
                this.lastPositionTime = performance.now();
                this.updateCurrentLine(newPosition);
                this.isDraggingScrubber = false;
            });

            this.timelineContainer.addEventListener('mouseenter', () => {
                this.timelineContainer.classList.add('visible');
            });

            this.timelineContainer.addEventListener('mouseleave', () => {
                this.scheduleTimelineHide();
            });
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.lyricScroll = new LyricScroll();
});
