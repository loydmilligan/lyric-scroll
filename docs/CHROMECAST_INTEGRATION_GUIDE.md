# Chromecast Custom Receiver Integration Guide

## Overview

This document explains how to integrate Chromecast casting of arbitrary web content (dashboards, pages, dynamic content) into a Home Assistant addon. This approach uses Google's **Custom Receiver** architecture, which allows you to run your own HTML/JS directly on the Chromecast device.

**Key Insight**: Unlike media casting (videos, audio), displaying custom web content requires a registered Custom Receiver application with Google. There is no workaround for this - it's how Chromecast's security model works.

---

## Recommended Approach: PyChromecast (Backend/Automatic)

For automatic casting (no user interaction), use **PyChromecast** from the addon backend. This is the approach used by Home Assistant's built-in cast integration.

**Advantages:**
- Fully automatic - no browser, no clicks
- Works from Python backend
- Can reconnect automatically
- Perfect for event-driven casting (e.g., when a song starts playing)

**The alternative (Browser Cast SDK)** requires a user click to initiate and a browser tab to stay open - not suitable for automatic casting.

### PyChromecast Module

Copy `chromecast_caster.py` to your addon. Usage:

```python
from chromecast_caster import ChromecastCaster, cast_to_device

# Simple one-shot casting
cast_to_device(
    device_ip="192.168.5.187",
    url="http://192.168.4.217:8080/lyrics?song=123",
    app_id="76719249"
)

# Or for persistent connection (recommended for frequent updates)
caster = ChromecastCaster(app_id="76719249")
caster.connect("192.168.5.187")
caster.launch_receiver()

# Cast different URLs as songs change
caster.cast_url("http://ha-ip:port/lyrics?song=song1")
# ... later ...
caster.cast_url("http://ha-ip:port/lyrics?song=song2")

# When done
caster.clear_content()
caster.disconnect()
```

### Integration with Home Assistant Events

```python
# Example: Cast lyrics when media player starts playing
async def handle_media_player_state_change(event):
    state = event.data.get("new_state")

    if state.state == "playing":
        media_title = state.attributes.get("media_title")
        song_id = lookup_song_id(media_title)

        lyrics_url = f"http://{HA_IP}:{ADDON_PORT}/lyrics/{song_id}"

        caster.cast_url(lyrics_url)

    elif state.state in ("paused", "idle"):
        caster.clear_content()
```

### Dependencies

Add to your addon's requirements:
```
pychromecast>=14.0.0
```

---

## Cast Receiver Deployment

The custom receiver is deployed as a Docker container on a separate host (piUSBcam). This keeps it running 24/7 independently of the Home Assistant addon.

### Production Deployment

| Setting | Value |
|---------|-------|
| Host | piUSBcam (192.168.4.158) |
| Port | 9123 |
| Receiver URL | `http://192.168.4.158:9123/receiver.html` |
| Repository | https://github.com/loydmilligan/cast-receiver |

### Deploying Updates

When changes are made to the receiver:

```bash
# Push changes from development machine
cd ~/Projects/cast-test
git add <files>
git commit -m "Description of changes"
git push

# Deploy on Pi
ssh pi "cd ~/cast-receiver && git pull && docker compose up -d --build"
```

### Useful Commands

```bash
# Check container status
ssh pi "docker ps --filter name=cast-receiver"

# View logs
ssh pi "docker logs cast-receiver"
ssh pi "docker logs -f cast-receiver"  # Follow logs

# Restart container
ssh pi "cd ~/cast-receiver && docker compose restart"

# Full redeploy
ssh pi "cd ~/cast-receiver && docker compose down && docker compose up -d --build"
```

### Container Configuration

The container runs with `restart: unless-stopped` policy, so it will:
- Automatically restart if it crashes
- Restart after Docker/system reboot
- Stay stopped only if manually stopped

---

## Manual Casting (Backup/Testing)

The browser-based sender is available as a backup for testing or debugging. Unlike PyChromecast, this requires manual user interaction.

### When to Use Manual Casting
- Testing receiver changes before deploying
- Debugging casting issues
- Verifying Chromecast connectivity
- Quick one-off casts without backend

### How to Use

1. Open Chrome browser (required - Cast SDK only works in Chrome)
2. Navigate to `http://localhost:8080/sender.html` (must use localhost, not IP)
3. Enter App ID: `76719249`
4. Click "Initialize Cast"
5. Click "Start Casting" - select your Chromecast from the dialog
6. Enter a URL and click "Cast URL"

**Note:** The sender must be accessed via `localhost` because Chrome's Cast SDK requires a secure context (HTTPS or localhost).

### Limitations of Manual Casting
- Requires Chrome browser
- Requires user click to initiate (cannot be automated)
- Browser tab must stay open to maintain session
- Not suitable for automatic/event-driven casting

For production use with Home Assistant automations, always use PyChromecast.

---

## Architecture

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│   HA Addon      │         │   Google Cast   │         │   Chromecast    │
│   (Sender)      │ ──────► │   Cloud         │ ──────► │   (Receiver)    │
│                 │         │                 │         │                 │
│ - Initiates cast│         │ - Routes session│         │ - Loads receiver│
│ - Sends messages│         │ - App ID lookup │         │   HTML from URL │
│ - Controls      │         │                 │         │ - Runs your code│
└─────────────────┘         └─────────────────┘         └─────────────────┘
```

### Components

1. **Sender**: The Home Assistant addon frontend that initiates the cast and sends commands
2. **Receiver**: An HTML page hosted by the addon that runs ON the Chromecast
3. **Cast Application ID**: A unique ID from Google that links sender to receiver
4. **Custom Message Namespace**: A channel for sender↔receiver communication

---

## Prerequisites

### 1. Google Cast Developer Account ($5 one-time fee)

1. Go to: https://cast.google.com/publish
2. Pay the $5 registration fee (one-time, permanent)
3. This gives access to register Custom Receiver applications

### 2. Register a Custom Receiver Application

1. In the Cast Developer Console, click **"Add New Application"**
2. Select **"Custom Receiver"**
3. Fill in:
   - **Name**: Your addon name (e.g., "HA Dashboard Cast")
   - **Receiver Application URL**: `http://<HA_IP>:<ADDON_PORT>/receiver.html`
4. Save and note the **Application ID** (e.g., `76719249`)

### 3. Register Chromecast Devices for Testing

**IMPORTANT**: Until you publish the app (requires HTTPS), each Chromecast must be registered as a test device.

1. In Cast Developer Console, click on your application
2. Click **"Add Cast Receiver Device"**
3. Enter the Chromecast's **serial number**
   - Found in Google Home app: Device → Settings (gear) → scroll to bottom
   - Or printed on the physical device
4. Add a description (e.g., "Living Room Chromecast")
5. **Reboot the Chromecast** (unplug power, wait 10 sec, plug back in)

The device status will show "Ready For Testing" once registered.

---

## Information Required from Users

The addon settings UI should collect:

| Field | Description | Example |
|-------|-------------|---------|
| `cast_app_id` | Application ID from Cast Console | `76719249` |
| `chromecast_devices` | List of registered device serial numbers | `["6920103PYB5A"]` |
| `chromecast_ip` | IP address of the Chromecast device | `192.168.5.187` |

**Note on Chromecast IP Address**: When using PyChromecast for automatic casting, you need the Chromecast's IP address. While PyChromecast supports device discovery via mDNS, discovery may not work reliably in all network setups (Docker containers, WSL, complex network configurations). For production use, it's recommended to ask users to provide the Chromecast IP address in the addon settings. Users can find this in the Google Home app under Device Settings → Technical Information.

### Optional (if you want device discovery):
The addon can use mDNS/SSDP to discover Chromecasts on the network, but users still need to register serial numbers in Cast Console for unpublished apps.

---

## Implementation

### File Structure

```
addon/
├── receiver/
│   └── receiver.html      # Runs ON the Chromecast
├── static/
│   └── cast-sender.js     # Sender-side Cast logic
├── templates/
│   └── dashboard.html     # HA addon UI with cast controls
└── config.yaml            # Addon configuration
```

---

### Receiver HTML (runs on Chromecast)

This file must be served at the URL registered in Cast Console.

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>HA Cast Receiver</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: #1a1a2e;
      color: white;
      height: 100vh;
      width: 100vw;
      overflow: hidden;
    }

    /* Default view when no URL is loaded */
    .standby {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100vh;
      text-align: center;
    }

    .standby h1 {
      font-size: 48px;
      margin-bottom: 20px;
    }

    .standby .status {
      font-size: 24px;
      opacity: 0.7;
    }

    /* Iframe for displaying cast content */
    #contentFrame {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      border: none;
      z-index: 1000;
    }

    #contentFrame.active {
      display: block;
    }
  </style>
</head>
<body>
  <div class="standby" id="standbyView">
    <h1>Home Assistant</h1>
    <div class="status" id="status">Ready to receive content</div>
  </div>

  <iframe id="contentFrame"></iframe>

  <!-- Cast Receiver SDK - REQUIRED -->
  <script src="//www.gstatic.com/cast/sdk/libs/caf_receiver/v3/cast_receiver_framework.js"></script>

  <script>
    // Custom namespace for sender↔receiver messages
    // MUST match the namespace used in sender code
    const NAMESPACE = 'urn:x-cast:com.yourcompany.hacast';

    // Initialize Cast Receiver
    const context = cast.framework.CastReceiverContext.getInstance();
    const playerManager = context.getPlayerManager();

    // Handle messages from sender
    context.addCustomMessageListener(NAMESPACE, (event) => {
      console.log('Received message:', event.data);
      const data = event.data;

      // Load a URL in the iframe
      if (data.loadUrl) {
        loadContent(data.loadUrl);
      }

      // Clear content and show standby
      if (data.clearContent) {
        clearContent();
      }

      // Update status message
      if (data.statusMessage) {
        document.getElementById('status').textContent = data.statusMessage;
      }

      // Reload current content
      if (data.reload) {
        const frame = document.getElementById('contentFrame');
        if (frame.src) {
          frame.src = frame.src;
        }
      }
    });

    function loadContent(url) {
      const frame = document.getElementById('contentFrame');
      const standby = document.getElementById('standbyView');

      frame.src = url;
      frame.classList.add('active');
      standby.style.display = 'none';

      console.log('Loading content:', url);
    }

    function clearContent() {
      const frame = document.getElementById('contentFrame');
      const standby = document.getElementById('standbyView');

      frame.src = '';
      frame.classList.remove('active');
      standby.style.display = 'flex';

      console.log('Content cleared');
    }

    // Start the receiver with options
    const options = new cast.framework.CastReceiverOptions();
    options.disableIdleTimeout = true;  // Keep receiver alive indefinitely
    options.maxInactivity = 3600;       // 1 hour max inactivity

    context.start(options);
    console.log('Cast receiver started');
  </script>
</body>
</html>
```

---

### Sender JavaScript (runs in HA addon frontend)

```javascript
// Cast Sender Module for Home Assistant Addon
// Include Cast SDK in your HTML:
// <script src="https://www.gstatic.com/cv/js/sender/v1/cast_sender.js?loadCastFramework=1"></script>

class HACastSender {
  constructor(appId) {
    this.appId = appId;
    this.namespace = 'urn:x-cast:com.yourcompany.hacast';
    this.session = null;
    this.isReady = false;
    this.onStatusChange = null;  // Callback for UI updates

    this._initializeCast();
  }

  _initializeCast() {
    // Wait for Cast API to be available
    window['__onGCastApiAvailable'] = (isAvailable) => {
      if (isAvailable) {
        this._setupCast();
      } else {
        console.error('Cast API not available');
        this._updateStatus('error', 'Cast not available in this browser');
      }
    };
  }

  _setupCast() {
    cast.framework.CastContext.getInstance().setOptions({
      receiverApplicationId: this.appId,
      autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED
    });

    const context = cast.framework.CastContext.getInstance();

    context.addEventListener(
      cast.framework.CastContextEventType.SESSION_STATE_CHANGED,
      (event) => this._handleSessionStateChange(event)
    );

    context.addEventListener(
      cast.framework.CastContextEventType.CAST_STATE_CHANGED,
      (event) => this._handleCastStateChange(event)
    );

    this.isReady = true;
    this._updateStatus('ready', 'Cast ready');
  }

  _handleSessionStateChange(event) {
    const state = event.sessionState;

    if (state === cast.framework.SessionState.SESSION_STARTED ||
        state === cast.framework.SessionState.SESSION_RESUMED) {
      this.session = cast.framework.CastContext.getInstance().getCurrentSession();
      const deviceName = this.session.getCastDevice().friendlyName;
      this._updateStatus('connected', `Connected to ${deviceName}`);
    } else if (state === cast.framework.SessionState.SESSION_ENDED) {
      this.session = null;
      this._updateStatus('disconnected', 'Disconnected');
    }
  }

  _handleCastStateChange(event) {
    const state = event.castState;
    if (state === cast.framework.CastState.NO_DEVICES_AVAILABLE) {
      this._updateStatus('no_devices', 'No Chromecast devices found');
    }
  }

  _updateStatus(state, message) {
    if (this.onStatusChange) {
      this.onStatusChange(state, message);
    }
    console.log(`Cast status: ${state} - ${message}`);
  }

  // Public Methods

  /**
   * Start a cast session - opens Chrome's cast dialog
   */
  async startCasting() {
    if (!this.isReady) {
      throw new Error('Cast not ready');
    }

    try {
      await cast.framework.CastContext.getInstance().requestSession();
    } catch (err) {
      if (err === 'cancel') {
        console.log('User cancelled cast dialog');
      } else {
        throw err;
      }
    }
  }

  /**
   * Stop the current cast session
   */
  stopCasting() {
    if (this.session) {
      this.session.endSession(true);
    }
  }

  /**
   * Check if currently casting
   */
  isConnected() {
    return this.session !== null;
  }

  /**
   * Cast a URL to the receiver
   * @param {string} url - The URL to display on the Chromecast
   */
  async castUrl(url) {
    if (!this.session) {
      throw new Error('Not connected to Chromecast');
    }

    await this.session.sendMessage(this.namespace, { loadUrl: url });
    console.log(`Casting URL: ${url}`);
  }

  /**
   * Clear content and show standby screen
   */
  async clearContent() {
    if (!this.session) {
      throw new Error('Not connected to Chromecast');
    }

    await this.session.sendMessage(this.namespace, { clearContent: true });
  }

  /**
   * Reload the current content
   */
  async reloadContent() {
    if (!this.session) {
      throw new Error('Not connected to Chromecast');
    }

    await this.session.sendMessage(this.namespace, { reload: true });
  }

  /**
   * Send a custom message to the receiver
   * @param {object} data - Any JSON-serializable data
   */
  async sendMessage(data) {
    if (!this.session) {
      throw new Error('Not connected to Chromecast');
    }

    await this.session.sendMessage(this.namespace, data);
  }
}

// Export for use in addon
window.HACastSender = HACastSender;
```

---

### Example HTML UI for Addon

```html
<!DOCTYPE html>
<html>
<head>
  <title>HA Cast Control</title>
  <script src="https://www.gstatic.com/cv/js/sender/v1/cast_sender.js?loadCastFramework=1"></script>
</head>
<body>
  <h1>Chromecast Control</h1>

  <div id="status">Initializing...</div>

  <div id="controls" style="display:none;">
    <button id="castBtn">Start Casting</button>

    <div id="connectedControls" style="display:none;">
      <input type="text" id="urlInput" placeholder="URL to cast">
      <button id="castUrlBtn">Cast URL</button>
      <button id="clearBtn">Clear</button>
      <button id="stopBtn">Stop Casting</button>
    </div>
  </div>

  <script src="/static/cast-sender.js"></script>
  <script>
    // Get app ID from addon config (injected by backend)
    const APP_ID = '{{ cast_app_id }}';  // Template variable from backend

    const caster = new HACastSender(APP_ID);

    caster.onStatusChange = (state, message) => {
      document.getElementById('status').textContent = message;

      const connectedControls = document.getElementById('connectedControls');
      const castBtn = document.getElementById('castBtn');

      if (state === 'connected') {
        connectedControls.style.display = 'block';
        castBtn.style.display = 'none';
      } else {
        connectedControls.style.display = 'none';
        castBtn.style.display = 'block';
      }

      if (state === 'ready' || state === 'disconnected') {
        document.getElementById('controls').style.display = 'block';
      }
    };

    document.getElementById('castBtn').onclick = () => caster.startCasting();
    document.getElementById('stopBtn').onclick = () => caster.stopCasting();
    document.getElementById('clearBtn').onclick = () => caster.clearContent();

    document.getElementById('castUrlBtn').onclick = () => {
      const url = document.getElementById('urlInput').value;
      if (url) caster.castUrl(url);
    };
  </script>
</body>
</html>
```

---

## Network Requirements

### Critical: Sender Page Must Use Secure Context

The Cast Sender SDK **only works** in secure contexts:
- `https://...` (any origin)
- `http://localhost:...`
- `http://127.0.0.1:...`

**For Home Assistant**: If accessing HA via `http://192.168.x.x`, the Cast SDK will fail. Solutions:
1. Access HA via `https://` (recommended - set up SSL)
2. Access via `http://localhost:8123` if on the same machine
3. Use Ingress (addon iframe) which may inherit HA's context

### Receiver Must Be Accessible from Chromecast

The receiver URL (registered in Cast Console) must be:
- Accessible from the Chromecast's network
- Using the server's LAN IP, not `localhost`
- Example: `http://192.168.4.217:8080/receiver.html`

### Content URLs Must Be Accessible from Chromecast

Any URL you cast (via `castUrl()`) must be:
- On the same network as the Chromecast
- Not blocked by CORS or X-Frame-Options headers
- Using LAN IP addresses, not `localhost`

---

## Adding More Chromecast Devices

### Process for Each New Device

1. **Get the serial number** from Google Home app or device itself
2. **Add to Cast Developer Console**:
   - Go to https://cast.google.com/publish
   - Click on your application
   - Click "Add Cast Receiver Device"
   - Enter serial number and description
3. **Reboot the Chromecast** (required for it to fetch the new config)
4. **Optionally update addon config** if tracking devices

### Addon Settings UI Suggestion

```yaml
# Example addon config schema
schema:
  cast_app_id:
    type: string
    required: true
    description: "Application ID from Google Cast Developer Console"

  registered_devices:
    type: list
    required: false
    description: "List of registered Chromecast devices (for reference)"
    items:
      type: object
      properties:
        serial:
          type: string
        name:
          type: string
        location:
          type: string
```

---

## Publishing the Application (Optional)

For production use without registering individual devices:

### Requirements
1. **HTTPS receiver URL** - Must use SSL certificate
2. **Sender application details** - Platform info in Cast Console
3. **Google review** - May take several days

### Steps
1. Set up HTTPS for your addon (Let's Encrypt, etc.)
2. Update receiver URL in Cast Console to use `https://`
3. Add sender application details (Chrome/Web)
4. Click "Publish" and wait for approval

Once published, any Chromecast can use the app without being registered as a test device.

---

## Troubleshooting

### "No devices found" in cast dialog
- Chromecast not registered as test device in Cast Console
- Chromecast not rebooted after registration
- Serial number mismatch
- Chromecast on different network/VLAN

### "Cast API not available"
- Not using Chrome browser
- Not using secure context (needs HTTPS or localhost)
- Incognito mode
- Cast extension disabled

### Receiver shows but content doesn't load
- Content URL not accessible from Chromecast network
- Content blocked by X-Frame-Options
- Content using localhost instead of LAN IP
- CORS issues

### Cast connects but receiver doesn't appear
- Receiver URL in Cast Console is wrong
- Receiver HTML has JavaScript errors
- Receiver not accessible from internet (Google needs to verify URL)

---

## Quick Reference

| Item | Value |
|------|-------|
| Cast Console | https://cast.google.com/publish |
| Sender SDK | `https://www.gstatic.com/cv/js/sender/v1/cast_sender.js?loadCastFramework=1` |
| Receiver SDK | `//www.gstatic.com/cast/sdk/libs/caf_receiver/v3/cast_receiver_framework.js` |
| Namespace format | `urn:x-cast:com.yourcompany.appname` |
| Test device reboot | Required after adding to Cast Console |
| Receiver Deployment | `ssh pi "cd ~/cast-receiver && git pull && docker compose up -d --build"` |
| Receiver URL | `http://192.168.4.158:9123/receiver.html` |

---

## Summary

1. **Register** a Custom Receiver app in Cast Console ($5 one-time)
2. **Host** the receiver HTML at a URL accessible from Chromecast
3. **Register** each Chromecast as a test device (until published)
4. **Include** Cast Sender SDK in your addon frontend
5. **Use** HACastSender class to control casting
6. **Ensure** sender page uses HTTPS or localhost
7. **Ensure** all content URLs use LAN IPs, not localhost
