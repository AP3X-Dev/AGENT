#!/usr/bin/env python3
"""
WebSocket server for live browser streaming using Playwright.
Streams CDP screencast frames to the frontend and handles user input.

Run with: python browser_ws_server.py
Listens on ws://localhost:8765 by default.

Performance tuning via environment variables:
  BROWSER_WS_JPEG_QUALITY=55      # JPEG quality 10-100 (default: 55, balanced)
  BROWSER_WS_EVERY_NTH_FRAME=1    # Frame skip 1-10 (default: 1, every frame)
  BROWSER_WS_MAX_WIDTH=1280       # Max frame width (default: viewport width)
  BROWSER_WS_MAX_HEIGHT=720       # Max frame height (default: viewport height)
  BROWSER_WS_STEALTH=true         # Enable anti-bot evasion (default: true)
  BROWSER_WS_DEBUG=false          # Enable debug logging (default: false)

Note: The client uses adaptive quality adjustment with hysteresis to prevent
quality bouncing. Quality changes require sustained conditions before applying.
"""
import asyncio
import base64
import json
import logging
import os
import random
import signal
import sys
import subprocess
import time
from enum import Enum
from typing import Optional

# Configure logging
DEBUG_MODE = os.environ.get("BROWSER_WS_DEBUG", "false").lower() in ("true", "1", "yes")
logging.basicConfig(
    level=logging.DEBUG if DEBUG_MODE else logging.INFO,
    format="[%(asctime)s] [BrowserWS] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class ErrorCode(Enum):
    """Standardized error codes for client communication."""
    BROWSER_LAUNCH_FAILED = "BROWSER_LAUNCH_FAILED"
    NAVIGATION_FAILED = "NAVIGATION_FAILED"
    INPUT_FAILED = "INPUT_FAILED"
    SCREENCAST_FAILED = "SCREENCAST_FAILED"
    SESSION_CLOSED = "SESSION_CLOSED"
    INVALID_MESSAGE = "INVALID_MESSAGE"
    URL_VALIDATION_FAILED = "URL_VALIDATION_FAILED"
    CONNECTION_ERROR = "CONNECTION_ERROR"


# WebSocket close codes (4000-4999 are application-specific)
# These tell the client whether to reconnect or not
class CloseCode:
    """WebSocket close codes for different scenarios."""
    NORMAL = 1000  # Normal closure - don't reconnect
    BROWSER_LAUNCH_FAILED = 4001  # Browser failed to launch - don't reconnect
    SCREENCAST_FAILED = 4002  # Screencast failed - don't reconnect
    SERVER_ERROR = 4003  # Server error - may reconnect
    RATE_LIMITED = 4004  # Too many connections - wait before reconnecting


def make_error_response(code: ErrorCode, message: str, details: str = "") -> dict:
    """Create a standardized error response for the client."""
    return {
        "type": "error",
        "code": code.value,
        "message": message,
        "details": details if DEBUG_MODE else "",
    }


# ============================================
# INPUT VALIDATION
# ============================================

# Allowed URL schemes
ALLOWED_URL_SCHEMES = {"http", "https", "file"}

# Max URL length to prevent DoS
MAX_URL_LENGTH = 8192

# Characters not allowed in keyboard input (control characters except common ones)
DISALLOWED_CHARS = set(chr(i) for i in range(32) if i not in (9, 10, 13))  # Allow tab, newline, carriage return


def validate_url(url: str) -> tuple[bool, str]:
    """
    Validate a URL for navigation.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url:
        return False, "URL is empty"

    if len(url) > MAX_URL_LENGTH:
        return False, f"URL exceeds maximum length of {MAX_URL_LENGTH} characters"

    # Check for URL injection attempts
    if "\n" in url or "\r" in url:
        return False, "URL contains invalid characters"

    # Parse the URL
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)

        # Check scheme
        if parsed.scheme and parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
            return False, f"URL scheme '{parsed.scheme}' is not allowed"

        # If no scheme, it might be a relative URL or search query - that's ok
        if not parsed.scheme and not parsed.netloc and not url.startswith("/"):
            # Could be a search query - let the browser handle it
            pass

        # Check for javascript: or data: URLs (XSS vectors)
        if parsed.scheme.lower() in ("javascript", "data", "vbscript"):
            return False, f"URL scheme '{parsed.scheme}' is not allowed for security reasons"

    except Exception as e:
        return False, f"Invalid URL format: {e}"

    return True, ""


def sanitize_keyboard_input(text: str, max_length: int = 10000) -> str:
    """
    Sanitize keyboard input text.

    Args:
        text: The text to sanitize
        max_length: Maximum allowed text length

    Returns:
        Sanitized text
    """
    if not text:
        return ""

    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length]

    # Remove disallowed control characters
    text = "".join(c for c in text if c not in DISALLOWED_CHARS)

    return text


def validate_coordinates(x: any, y: any, viewport_width: int = 1920, viewport_height: int = 1080) -> tuple[int, int]:
    """
    Validate and clamp mouse coordinates.

    Args:
        x: X coordinate (can be any type)
        y: Y coordinate (can be any type)
        viewport_width: Max X value
        viewport_height: Max Y value

    Returns:
        Tuple of (clamped_x, clamped_y)
    """
    try:
        x = int(float(x)) if x is not None else 0
        y = int(float(y)) if y is not None else 0
    except (ValueError, TypeError):
        x, y = 0, 0

    # Clamp to viewport bounds
    x = max(0, min(x, viewport_width))
    y = max(0, min(y, viewport_height))

    return x, y


# Fix Windows console encoding for unicode
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

def install_package(package: str):
    """Install a Python package."""
    logger.info(f"Installing {package}...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])

def install_playwright_browsers():
    """Install Playwright browsers."""
    logger.info("Installing Playwright browsers (this may take a minute)...")
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
    logger.info("Playwright browsers installed successfully!")

try:
    import websockets
    from websockets.asyncio.server import serve
except ImportError:
    install_package("websockets")
    import websockets
    from websockets.asyncio.server import serve

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
except ImportError:
    install_package("playwright")
    install_playwright_browsers()
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page

# Port configuration
WS_PORT = int(os.environ.get("BROWSER_WS_PORT", "8765"))
BROWSERS_INSTALLED = False

# Persistent browser profile directory
# Stores cookies, localStorage, IndexedDB, login sessions, etc.
BROWSER_PROFILE_DIR = os.environ.get(
    "BROWSER_WS_PROFILE_DIR",
    os.path.join(os.path.expanduser("~"), ".ag3nt", "browser-profile"),
)

# Maximum concurrent browser sessions (prevents resource exhaustion)
MAX_CONCURRENT_SESSIONS = int(os.environ.get("BROWSER_WS_MAX_SESSIONS", "1"))

# Stealth mode - helps avoid bot detection
STEALTH_MODE = os.environ.get("BROWSER_WS_STEALTH", "true").lower() in ("true", "1", "yes")

# Use system Chrome instead of Playwright's Chromium (more stealthy)
USE_SYSTEM_CHROME = os.environ.get("BROWSER_WS_USE_SYSTEM_CHROME", "true").lower() in ("true", "1", "yes")

# Shared Playwright instance management
# Using a single Playwright instance prevents "Connection closed while reading from the driver" errors
# that occur when multiple Playwright instances are started concurrently
_playwright_instance = None
_playwright_lock = asyncio.Lock()
_session_semaphore: asyncio.Semaphore | None = None


async def get_playwright():
    """Get or create the shared Playwright instance."""
    global _playwright_instance
    async with _playwright_lock:
        if _playwright_instance is None:
            logger.info("Starting shared Playwright instance...")
            _playwright_instance = await async_playwright().start()
            logger.info("Playwright instance started successfully")
        return _playwright_instance


async def shutdown_playwright():
    """Shutdown the shared Playwright instance."""
    global _playwright_instance
    async with _playwright_lock:
        if _playwright_instance is not None:
            logger.info("Stopping shared Playwright instance...")
            try:
                await _playwright_instance.stop()
            except Exception as e:
                logger.debug(f"Playwright stop error: {e}")
            _playwright_instance = None
            logger.info("Playwright instance stopped")

# Realistic user agents for stealth mode (Chrome 120-122 are current as of Jan 2026)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

def find_system_chrome() -> str | None:
    """Find the system Chrome/Chromium executable."""
    if sys.platform == "win32":
        # Common Windows Chrome paths
        paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles%\Chromium\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Chromium\Application\chrome.exe"),
        ]
    elif sys.platform == "darwin":
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:  # Linux
        paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ]

    for path in paths:
        if os.path.exists(path):
            logger.debug(f"Found system Chrome at: {path}")
            return path

    return None


class BrowserSession:
    """Manages a single Playwright browser session with CDP screencast."""

    def __init__(self, session_id: str, viewport_width: int = 1280, viewport_height: int = 720):
        self.session_id = session_id
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.cdp_session = None
        self.is_streaming = False
        self.frame_callback = None

        # Navigation history tracking
        self._nav_history: list[str] = []
        self._nav_index: int = -1

        # Streaming/backpressure — maxsize=2 lets the next frame queue while current sends
        self._frame_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=2)
        self._frame_sender_task: Optional[asyncio.Task] = None

        # Screencast tuning (env overrides) - balanced defaults for quality and performance
        # Start with "good" quality preset - client will adjust based on connection
        self.jpeg_quality = int(os.environ.get("BROWSER_WS_JPEG_QUALITY", "55"))  # Balanced quality
        self.every_nth_frame = max(1, int(os.environ.get("BROWSER_WS_EVERY_NTH_FRAME", "1")))  # Every frame initially
        self.max_width = int(os.environ.get("BROWSER_WS_MAX_WIDTH", "0"))
        self.max_height = int(os.environ.get("BROWSER_WS_MAX_HEIGHT", "0"))
    
    async def start(self, initial_url: str = "https://www.google.com"):
        """Start the browser with a persistent profile and begin screencast streaming.

        Uses launch_persistent_context() so cookies, localStorage, IndexedDB,
        and login sessions survive across restarts.  The profile directory
        defaults to ~/.ag3nt/browser-profile/ (overridable via
        BROWSER_WS_PROFILE_DIR env var).
        """
        global BROWSERS_INSTALLED

        # Use shared Playwright instance to prevent concurrent initialization issues
        self.playwright = await get_playwright()

        # Use headed mode for better anti-detection (user can see the browser)
        # Set BROWSER_WS_HEADLESS=true to force headless mode
        use_headless = os.environ.get("BROWSER_WS_HEADLESS", "false").lower() in ("true", "1", "yes")

        # Ensure profile directory exists
        os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
        logger.info(f"Using persistent browser profile: {BROWSER_PROFILE_DIR}")

        # Browser launch args - optimized for performance and stealth
        launch_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-hang-monitor",
            "--disable-ipc-flooding-protection",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-sync",
            "--disable-translate",
            "--metrics-recording-only",
            "--no-first-run",
            "--safebrowsing-disable-auto-update",
        ]

        # Add stealth args to avoid bot detection
        if STEALTH_MODE:
            launch_args.extend([
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-default-browser-check",
                "--disable-component-update",
                "--disable-domain-reliability",
                "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
                "--disable-print-preview",
                "--disable-setuid-sandbox",
                "--disable-site-isolation-trials",
                "--disable-speech-api",
                "--disable-web-security",
                "--hide-scrollbars",
                "--ignore-gpu-blocklist",
                "--mute-audio",
                "--no-pings",
                "--no-zygote",
                "--password-store=basic",
                "--use-gl=swiftshader",
                "--use-mock-keychain",
                "--single-process",
                # Window size to look like a real browser
                f"--window-size={self.viewport_width},{self.viewport_height}",
            ])

            # In headed mode, position window off-screen so it doesn't distract the user
            # The browser will still render and stream to the UI
            if not use_headless:
                launch_args.extend([
                    "--window-position=-2400,-2400",  # Position far off-screen
                ])

        # Try to use system Chrome for better stealth
        chrome_path = None
        if USE_SYSTEM_CHROME and STEALTH_MODE:
            chrome_path = find_system_chrome()
            if chrome_path:
                logger.info("Using system Chrome for better stealth")
            else:
                logger.info("System Chrome not found, using Playwright's Chromium")

        # Context options shared between persistent launch and context creation
        context_options: dict = {
            "viewport": {"width": self.viewport_width, "height": self.viewport_height},
        }

        if STEALTH_MODE:
            context_options["user_agent"] = random.choice(USER_AGENTS)
            context_options["locale"] = "en-US"
            context_options["timezone_id"] = "America/New_York"
            context_options["color_scheme"] = "light"
            context_options["permissions"] = ["geolocation"]

        # ── Launch with persistent profile ──────────────────────────────
        # launch_persistent_context() returns a BrowserContext directly
        # (no separate Browser handle) and persists all storage to disk.
        launch_kwargs: dict = {
            "headless": use_headless,
            "args": launch_args,
            "chromium_sandbox": False,
            **context_options,
        }
        if chrome_path:
            launch_kwargs["executable_path"] = chrome_path
            # Remove some args that might not work with system Chrome
            launch_kwargs["args"] = [a for a in launch_args if a not in ["--single-process", "--no-zygote"]]

        try:
            self.context = await self.playwright.chromium.launch_persistent_context(
                BROWSER_PROFILE_DIR, **launch_kwargs,
            )
        except Exception as e:
            error_str = str(e)
            if "Executable doesn't exist" in error_str and not BROWSERS_INSTALLED:
                logger.info("Browser not found, installing...")
                install_playwright_browsers()
                BROWSERS_INSTALLED = True
                self.context = await self.playwright.chromium.launch_persistent_context(
                    BROWSER_PROFILE_DIR,
                    headless=use_headless,
                    args=launch_args,
                    chromium_sandbox=False,
                    **context_options,
                )
            elif "Connection closed while reading from the driver" in error_str:
                logger.error("Chrome crashed during launch. Possible causes:")
                logger.error("  1. Resource exhaustion (memory/CPU)")
                logger.error("  2. Chrome binary is corrupt or incompatible")
                logger.error("  3. Conflicting Chrome flags")
                logger.error("  4. System Chrome not compatible with Playwright")
                if chrome_path:
                    logger.info("Retrying with Playwright's Chromium instead of system Chrome...")
                    try:
                        self.context = await self.playwright.chromium.launch_persistent_context(
                            BROWSER_PROFILE_DIR,
                            headless=use_headless,
                            args=["--no-sandbox", "--disable-dev-shm-usage"],
                            chromium_sandbox=False,
                            **context_options,
                        )
                    except Exception as retry_e:
                        logger.error(f"Retry also failed: {retry_e}")
                        raise e
                else:
                    raise
            else:
                raise

        # browser handle not available with persistent context; keep None
        self.browser = None

        # Reuse existing page if the profile already had one, otherwise create
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()

        # Apply stealth scripts before navigation
        if STEALTH_MODE:
            await self._apply_stealth_scripts()

        await self.page.goto(initial_url, wait_until="domcontentloaded")
        self._track_navigation(initial_url)

        # Create CDP session for screencast
        self.cdp_session = await self.context.new_cdp_session(self.page)
        return True

    async def _apply_stealth_scripts(self):
        """Apply comprehensive JavaScript patches to avoid bot detection."""
        if not self.page:
            return

        # Comprehensive stealth script based on puppeteer-extra-plugin-stealth
        await self.page.add_init_script("""
            // ============================================
            // NAVIGATOR PATCHES
            // ============================================

            // Hide webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true,
            });

            // Delete webdriver from navigator prototype
            delete Navigator.prototype.webdriver;

            // Override navigator.plugins to look like a real browser
            const makePluginArray = () => {
                const plugins = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
                ];
                const pluginArray = Object.create(PluginArray.prototype);
                plugins.forEach((p, i) => {
                    const plugin = Object.create(Plugin.prototype);
                    Object.defineProperties(plugin, {
                        name: { value: p.name, enumerable: true },
                        filename: { value: p.filename, enumerable: true },
                        description: { value: p.description, enumerable: true },
                        length: { value: 0, enumerable: true },
                    });
                    pluginArray[i] = plugin;
                });
                Object.defineProperty(pluginArray, 'length', { value: plugins.length });
                pluginArray.item = (i) => pluginArray[i] || null;
                pluginArray.namedItem = (name) => plugins.find(p => p.name === name) || null;
                pluginArray.refresh = () => {};
                return pluginArray;
            };
            Object.defineProperty(navigator, 'plugins', { get: makePluginArray, configurable: true });

            // Override navigator.mimeTypes
            const makeMimeTypeArray = () => {
                const mimeTypes = [
                    { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
                    { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format' },
                ];
                const mimeTypeArray = Object.create(MimeTypeArray.prototype);
                mimeTypes.forEach((m, i) => {
                    const mimeType = Object.create(MimeType.prototype);
                    Object.defineProperties(mimeType, {
                        type: { value: m.type, enumerable: true },
                        suffixes: { value: m.suffixes, enumerable: true },
                        description: { value: m.description, enumerable: true },
                        enabledPlugin: { value: navigator.plugins[0], enumerable: true },
                    });
                    mimeTypeArray[i] = mimeType;
                });
                Object.defineProperty(mimeTypeArray, 'length', { value: mimeTypes.length });
                mimeTypeArray.item = (i) => mimeTypeArray[i] || null;
                mimeTypeArray.namedItem = (name) => mimeTypes.find(m => m.type === name) || null;
                return mimeTypeArray;
            };
            Object.defineProperty(navigator, 'mimeTypes', { get: makeMimeTypeArray, configurable: true });

            // Override navigator.languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
                configurable: true,
            });

            // Override navigator.platform
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32',
                configurable: true,
            });

            // Override navigator.hardwareConcurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8,
                configurable: true,
            });

            // Override navigator.deviceMemory
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8,
                configurable: true,
            });

            // Override navigator.maxTouchPoints
            Object.defineProperty(navigator, 'maxTouchPoints', {
                get: () => 0,
                configurable: true,
            });

            // ============================================
            // CHROME OBJECT PATCHES
            // ============================================

            // Create realistic chrome object
            window.chrome = {
                app: {
                    isInstalled: false,
                    InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                    RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
                },
                runtime: {
                    OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
                    OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
                    PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
                    PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
                    PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
                    RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' },
                    connect: () => {},
                    sendMessage: () => {},
                },
                csi: () => {},
                loadTimes: () => ({
                    commitLoadTime: Date.now() / 1000,
                    connectionInfo: 'http/1.1',
                    finishDocumentLoadTime: Date.now() / 1000,
                    finishLoadTime: Date.now() / 1000,
                    firstPaintAfterLoadTime: 0,
                    firstPaintTime: Date.now() / 1000,
                    navigationType: 'Other',
                    npnNegotiatedProtocol: 'unknown',
                    requestTime: Date.now() / 1000,
                    startLoadTime: Date.now() / 1000,
                    wasAlternateProtocolAvailable: false,
                    wasFetchedViaSpdy: false,
                    wasNpnNegotiated: false,
                }),
            };

            // ============================================
            // PERMISSIONS API PATCH
            // ============================================

            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => {
                if (parameters.name === 'notifications') {
                    return Promise.resolve({ state: Notification.permission, onchange: null });
                }
                return originalQuery.call(navigator.permissions, parameters);
            };

            // ============================================
            // WEBGL PATCHES
            // ============================================

            const getParameterProxyHandler = {
                apply: function(target, thisArg, args) {
                    const param = args[0];
                    // UNMASKED_VENDOR_WEBGL
                    if (param === 37445) {
                        return 'Google Inc. (NVIDIA)';
                    }
                    // UNMASKED_RENDERER_WEBGL
                    if (param === 37446) {
                        return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0, D3D11)';
                    }
                    return Reflect.apply(target, thisArg, args);
                }
            };

            // Patch WebGL
            const getContext = HTMLCanvasElement.prototype.getContext;
            HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                const context = getContext.call(this, type, ...args);
                if (context && (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl')) {
                    const originalGetParameter = context.getParameter.bind(context);
                    context.getParameter = new Proxy(originalGetParameter, getParameterProxyHandler);
                }
                return context;
            };

            // ============================================
            // IFRAME CONTENTWINDOW PATCH
            // ============================================

            // Prevent iframe detection
            try {
                Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
                    get: function() {
                        return window;
                    }
                });
            } catch (e) {}

            // ============================================
            // CONSOLE.DEBUG PATCH
            // ============================================

            // Some sites check if console.debug is native
            const originalDebug = console.debug;
            console.debug = function(...args) {
                return originalDebug.apply(console, args);
            };
            console.debug.toString = () => 'function debug() { [native code] }';

            // ============================================
            // NOTIFICATION PATCH
            // ============================================

            // Override Notification.permission
            Object.defineProperty(Notification, 'permission', {
                get: () => 'default',
                configurable: true,
            });

            // ============================================
            // SCREEN PATCHES
            // ============================================

            Object.defineProperty(screen, 'availWidth', { get: () => 1920, configurable: true });
            Object.defineProperty(screen, 'availHeight', { get: () => 1040, configurable: true });
            Object.defineProperty(screen, 'width', { get: () => 1920, configurable: true });
            Object.defineProperty(screen, 'height', { get: () => 1080, configurable: true });
            Object.defineProperty(screen, 'colorDepth', { get: () => 24, configurable: true });
            Object.defineProperty(screen, 'pixelDepth', { get: () => 24, configurable: true });

            // ============================================
            // OUTERWIDTH/HEIGHT PATCHES
            // ============================================

            Object.defineProperty(window, 'outerWidth', { get: () => 1920, configurable: true });
            Object.defineProperty(window, 'outerHeight', { get: () => 1040, configurable: true });
        """)
    
    async def start_screencast(self, on_frame):
        """Start streaming frames via CDP screencast."""
        self.frame_callback = on_frame
        self.is_streaming = True

        # Background sender loop: always send only the latest frame (queue maxsize=1)
        if self._frame_sender_task and not self._frame_sender_task.done():
            try:
                self._frame_sender_task.cancel()
            except Exception:
                pass
        self._frame_sender_task = asyncio.create_task(self._frame_sender_loop())
        
        # Listen for screencast frames
        self.cdp_session.on("Page.screencastFrame", self._handle_frame)
        
        # Start screencast
        max_w = self.viewport_width if self.max_width <= 0 else min(self.viewport_width, self.max_width)
        max_h = self.viewport_height if self.max_height <= 0 else min(self.viewport_height, self.max_height)
        await self.cdp_session.send("Page.startScreencast", {
            "format": "jpeg",
            "quality": self.jpeg_quality,
            "maxWidth": max_w,
            "maxHeight": max_h,
            "everyNthFrame": self.every_nth_frame,
        })

    async def _frame_sender_loop(self):
        """Send frames to the client with backpressure (drop old frames)."""
        while self.is_streaming:
            try:
                frame = await self._frame_queue.get()
                if not self.is_streaming:
                    break
                if self.frame_callback:
                    await self.frame_callback(frame)
            except asyncio.CancelledError:
                logger.debug("Frame sender loop cancelled")
                break
            except Exception as e:
                logger.debug(f"Sender loop error: {e}")
    
    async def _handle_frame(self, event):
        """Handle incoming screencast frame."""
        if not self.is_streaming:
            return
        
        try:
            # Fire-and-forget ack — don't await, avoids blocking the frame handler
            asyncio.ensure_future(
                self.cdp_session.send("Page.screencastFrameAck", {
                    "sessionId": event["sessionId"]
                })
            )

            # Decode CDP base64 payload to raw JPEG bytes and send as binary WS frame
            frame = base64.b64decode(event["data"])

            # Drop old frame if sender is still busy
            if self._frame_queue.full():
                try:
                    _ = self._frame_queue.get_nowait()
                except Exception:
                    pass
            try:
                self._frame_queue.put_nowait(frame)
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Frame error: {e}")

    async def stop_screencast(self):
        """Stop screencast streaming."""
        logger.debug(f"Stopping screencast for session {self.session_id}")
        self.is_streaming = False

        if self._frame_sender_task and not self._frame_sender_task.done():
            try:
                self._frame_sender_task.cancel()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"Frame sender cancel error: {e}")

        if self.cdp_session:
            try:
                await self.cdp_session.send("Page.stopScreencast")
            except Exception as e:
                logger.debug(f"Stop screencast error: {e}")

    async def handle_input(self, msg: dict):
        """Handle input events from the client with comprehensive validation and error handling."""
        if not self.page:
            return make_error_response(
                ErrorCode.SESSION_CLOSED,
                "Browser session not available"
            )

        try:
            msg_type = msg.get("type")

            if msg_type == "mouse_move":
                # Mouse move is high-frequency - use steps=0 for instant move
                # Validate and clamp coordinates
                x, y = validate_coordinates(
                    msg.get("x", 0),
                    msg.get("y", 0),
                    self.viewport_width,
                    self.viewport_height
                )
                await self.page.mouse.move(x, y, steps=0)

            elif msg_type == "mouse_down":
                button = msg.get("button", "left")
                if button not in ("left", "right", "middle"):
                    button = "left"
                await self.page.mouse.down(button=button)

            elif msg_type == "mouse_up":
                button = msg.get("button", "left")
                if button not in ("left", "right", "middle"):
                    button = "left"
                await self.page.mouse.up(button=button)

            elif msg_type == "mouse_wheel":
                # Batch scroll events - validate and clamp deltaY
                try:
                    delta_y = int(float(msg.get("deltaY", 0)))
                    # Clamp to reasonable scroll amount
                    delta_y = max(-10000, min(10000, delta_y))
                except (ValueError, TypeError):
                    delta_y = 0
                await self.page.mouse.wheel(0, delta_y)

            elif msg_type == "click":
                # Validate and clamp coordinates
                x, y = validate_coordinates(
                    msg.get("x", 0),
                    msg.get("y", 0),
                    self.viewport_width,
                    self.viewport_height
                )
                await self.page.mouse.click(x, y)

            elif msg_type == "key_down":
                key = msg.get("key", "")
                # Validate key - only allow non-empty strings up to reasonable length
                if key and isinstance(key, str) and len(key) <= 50:
                    await self.page.keyboard.down(key)

            elif msg_type == "key_up":
                key = msg.get("key", "")
                if key and isinstance(key, str) and len(key) <= 50:
                    await self.page.keyboard.up(key)

            elif msg_type == "type":
                text = msg.get("text", "")
                if text and isinstance(text, str):
                    # Sanitize the text input
                    sanitized_text = sanitize_keyboard_input(text)
                    if sanitized_text:
                        # Type with zero delay for minimal input latency
                        await self.page.keyboard.type(sanitized_text, delay=0)

            elif msg_type == "goto":
                url = msg.get("url", "")
                if url:
                    # Validate the URL before navigation
                    is_valid, error_msg = validate_url(url)
                    if not is_valid:
                        logger.warning(f"URL validation failed: {error_msg}")
                        return make_error_response(
                            ErrorCode.URL_VALIDATION_FAILED,
                            error_msg
                        )
                    try:
                        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        self._track_navigation(url)
                    except Exception as e:
                        logger.warning(f"Navigation error: {e}")
                        return make_error_response(
                            ErrorCode.NAVIGATION_FAILED,
                            f"Failed to navigate to {url}",
                            str(e)
                        )

            elif msg_type == "set_quality":
                # Adaptive quality adjustment from client
                # Only restart screencast if settings actually changed significantly
                new_quality = msg.get("jpegQuality")
                new_nth_frame = msg.get("everyNthFrame")

                old_quality = self.jpeg_quality
                old_nth_frame = self.every_nth_frame
                quality_changed = False

                if new_quality is not None:
                    try:
                        new_quality = int(new_quality)
                        # Clamp to valid range (10-100)
                        new_quality = max(10, min(100, new_quality))
                        # Only update if changed by at least 5 points (reduces restarts)
                        if abs(new_quality - self.jpeg_quality) >= 5:
                            self.jpeg_quality = new_quality
                            quality_changed = True
                            logger.debug(f"Quality adjusted: {old_quality} -> {self.jpeg_quality}")
                    except (ValueError, TypeError):
                        pass

                if new_nth_frame is not None:
                    try:
                        new_nth_frame = int(new_nth_frame)
                        # Clamp to valid range (1-10)
                        new_nth_frame = max(1, min(10, new_nth_frame))
                        if new_nth_frame != self.every_nth_frame:
                            self.every_nth_frame = new_nth_frame
                            quality_changed = True
                            logger.debug(f"Frame skip adjusted: {old_nth_frame} -> {self.every_nth_frame}")
                    except (ValueError, TypeError):
                        pass

                # Only restart screencast if settings actually changed
                if quality_changed and self.is_streaming and self.cdp_session:
                    try:
                        await self.cdp_session.send("Page.stopScreencast")
                        max_w = self.viewport_width if self.max_width <= 0 else min(self.viewport_width, self.max_width)
                        max_h = self.viewport_height if self.max_height <= 0 else min(self.viewport_height, self.max_height)
                        await self.cdp_session.send("Page.startScreencast", {
                            "format": "jpeg",
                            "quality": self.jpeg_quality,
                            "maxWidth": max_w,
                            "maxHeight": max_h,
                            "everyNthFrame": self.every_nth_frame,
                        })
                        logger.info(f"Screencast restarted with quality={self.jpeg_quality}, everyNthFrame={self.every_nth_frame}")
                    except Exception as e:
                        logger.warning(f"Failed to restart screencast with new quality: {e}")

            elif msg_type in ("goBack", "back"):
                try:
                    await self.page.go_back(wait_until="domcontentloaded", timeout=10000)
                    self._track_back()
                except Exception as e:
                    logger.debug(f"Go back error: {e}")

            elif msg_type in ("goForward", "forward"):
                try:
                    await self.page.go_forward(wait_until="domcontentloaded", timeout=10000)
                    self._track_forward()
                except Exception as e:
                    logger.debug(f"Go forward error: {e}")

            elif msg_type == "reload":
                try:
                    await self.page.reload(wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.debug(f"Reload error: {e}")

            elif msg_type == "click_selector":
                # Click by CSS selector (used by agent bridge)
                selector = msg.get("selector", "")
                if selector and isinstance(selector, str) and len(selector) <= 500:
                    try:
                        await self.page.click(selector, timeout=5000)
                    except Exception as e:
                        logger.debug(f"Click selector error: {e}")
                        return make_error_response(ErrorCode.INPUT_FAILED, f"Click selector failed: {e}")

            elif msg_type == "stop":
                # Note: Playwright doesn't have a direct stop method
                pass

            elif msg_type == "set_viewport":
                # Dynamic viewport sizing (Phase 2A)
                new_w = msg.get("width")
                new_h = msg.get("height")
                if new_w and new_h:
                    try:
                        new_w = max(320, min(3840, int(new_w)))
                        new_h = max(240, min(2160, int(new_h)))
                        if new_w != self.viewport_width or new_h != self.viewport_height:
                            self.viewport_width = new_w
                            self.viewport_height = new_h
                            await self.page.set_viewport_size({"width": new_w, "height": new_h})
                            logger.info(f"Viewport resized to {new_w}x{new_h}")
                            # Restart screencast with new dimensions
                            if self.is_streaming and self.cdp_session:
                                await self.cdp_session.send("Page.stopScreencast")
                                max_w = new_w if self.max_width <= 0 else min(new_w, self.max_width)
                                max_h = new_h if self.max_height <= 0 else min(new_h, self.max_height)
                                await self.cdp_session.send("Page.startScreencast", {
                                    "format": "jpeg",
                                    "quality": self.jpeg_quality,
                                    "maxWidth": max_w,
                                    "maxHeight": max_h,
                                    "everyNthFrame": self.every_nth_frame,
                                })
                    except Exception as e:
                        logger.warning(f"Viewport resize error: {e}")

            elif msg_type == "screenshot":
                # Return a full PNG screenshot (for agent bridge)
                try:
                    screenshot_bytes = await self.page.screenshot(type="png")
                    b64_data = base64.b64encode(screenshot_bytes).decode("ascii")
                    return {"type": "screenshot_result", "data": b64_data}
                except Exception as e:
                    logger.warning(f"Screenshot error: {e}")
                    return make_error_response(ErrorCode.INPUT_FAILED, f"Screenshot failed: {e}")

            elif msg_type == "get_content":
                # Extract text content from the page or element (for agent bridge)
                selector = msg.get("selector")
                try:
                    if selector:
                        element = await self.page.query_selector(selector)
                        text = await element.inner_text() if element else f"Element not found: {selector}"
                    else:
                        text = await self.page.inner_text("body")
                    # Truncate to 100KB
                    if len(text) > 100_000:
                        text = text[:100_000] + "\n... (truncated)"
                    return {"type": "content_result", "text": text}
                except Exception as e:
                    logger.warning(f"Get content error: {e}")
                    return make_error_response(ErrorCode.INPUT_FAILED, f"Get content failed: {e}")

            else:
                logger.debug(f"Unknown message type: {msg_type}")

        except Exception as e:
            logger.warning(f"Input error ({msg.get('type', 'unknown')}): {e}")
            return make_error_response(
                ErrorCode.INPUT_FAILED,
                f"Input handling failed: {msg.get('type', 'unknown')}",
                str(e)
            )
        return None
    
    def _track_navigation(self, url: str):
        """Track a forward navigation in history."""
        # Trim forward history when navigating to a new page
        if self._nav_index < len(self._nav_history) - 1:
            self._nav_history = self._nav_history[:self._nav_index + 1]
        self._nav_history.append(url)
        self._nav_index = len(self._nav_history) - 1

    def _track_back(self):
        """Track a back navigation."""
        if self._nav_index > 0:
            self._nav_index -= 1

    def _track_forward(self):
        """Track a forward navigation."""
        if self._nav_index < len(self._nav_history) - 1:
            self._nav_index += 1

    @property
    def can_go_back(self) -> bool:
        return self._nav_index > 0

    @property
    def can_go_forward(self) -> bool:
        return self._nav_index < len(self._nav_history) - 1

    async def get_current_url(self) -> str:
        """Get the current page URL."""
        return self.page.url if self.page else ""

    async def get_page_title(self) -> str:
        """Get the current page title."""
        return await self.page.title() if self.page else ""
    
    async def close(self):
        """Clean up browser resources with proper error handling.

        With launch_persistent_context, closing the context shuts down the
        browser process and flushes cookies/storage to disk automatically.
        """
        logger.debug(f"Closing session {self.session_id}")
        self.is_streaming = False

        # Cancel frame sender task
        if self._frame_sender_task and not self._frame_sender_task.done():
            try:
                self._frame_sender_task.cancel()
                await asyncio.sleep(0.1)  # Give time for cancellation
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"Frame sender cancel error: {e}")

        # Detach CDP session
        if self.cdp_session:
            try:
                await self.cdp_session.detach()
            except Exception as e:
                logger.debug(f"CDP session detach error: {e}")

        # Close persistent context (this also shuts down the browser process
        # and flushes profile data — cookies, localStorage, etc. — to disk)
        if self.context:
            try:
                await self.context.close()
            except Exception as e:
                logger.debug(f"Context close error: {e}")

        # browser is None with persistent context, but guard just in case
        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                logger.debug(f"Browser close error: {e}")

        # Note: We don't stop Playwright here because it's a shared instance
        # It will be stopped when the server shuts down via shutdown_playwright()

        logger.debug(f"Session {self.session_id} closed successfully")


# Active sessions by websocket connection
active_sessions: dict[int, BrowserSession] = {}

# Shared session model: multiple WebSocket clients share one browser session.
# The first client creates the session; subsequent clients join it.
_shared_session: BrowserSession | None = None
_shared_clients: set = set()   # set of connected websocket objects
_shared_lock = None            # asyncio.Lock, initialised in main()

# Shutdown flag for graceful shutdown
_shutdown_event: asyncio.Event | None = None

# Rate limiting: track connection attempts per IP
# Format: {ip: [(timestamp, success), ...]}
_connection_attempts: dict[str, list[tuple[float, bool]]] = {}
_RATE_LIMIT_WINDOW = 10.0  # seconds
_RATE_LIMIT_MAX_ATTEMPTS = 5  # max attempts per window
_RATE_LIMIT_FAILURE_COOLDOWN = 30.0  # seconds to wait after repeated failures


def _check_rate_limit(client_ip: str) -> tuple[bool, str]:
    """Check if a client is rate limited.

    Returns (allowed, reason) tuple.
    """
    now = time.time()
    attempts = _connection_attempts.get(client_ip, [])

    # Clean old attempts
    attempts = [(t, s) for t, s in attempts if now - t < max(_RATE_LIMIT_WINDOW, _RATE_LIMIT_FAILURE_COOLDOWN)]
    _connection_attempts[client_ip] = attempts

    if not attempts:
        return True, ""

    # Check for repeated failures (all recent attempts failed)
    recent_failures = [t for t, s in attempts if not s and now - t < _RATE_LIMIT_FAILURE_COOLDOWN]
    if len(recent_failures) >= 3:
        wait_time = int(_RATE_LIMIT_FAILURE_COOLDOWN - (now - recent_failures[0]))
        return False, f"Too many failed attempts. Wait {wait_time}s before retrying."

    # Check rate limit window
    window_attempts = [t for t, s in attempts if now - t < _RATE_LIMIT_WINDOW]
    if len(window_attempts) >= _RATE_LIMIT_MAX_ATTEMPTS:
        return False, f"Too many connection attempts. Max {_RATE_LIMIT_MAX_ATTEMPTS} per {_RATE_LIMIT_WINDOW}s."

    return True, ""


def _record_attempt(client_ip: str, success: bool):
    """Record a connection attempt for rate limiting."""
    now = time.time()
    if client_ip not in _connection_attempts:
        _connection_attempts[client_ip] = []
    _connection_attempts[client_ip].append((now, success))


async def _broadcast_json(msg: dict, *, exclude=None):
    """Send a JSON message to all shared-session clients (except *exclude*)."""
    data = json.dumps(msg)
    for ws in list(_shared_clients):
        if ws is exclude:
            continue
        try:
            await ws.send(data)
        except Exception:
            pass


async def handle_connection(websocket):
    """Handle a WebSocket connection for browser streaming.

    Supports a *shared session* model: the first client creates the browser
    session; subsequent clients join the same session.  All clients receive
    screencast frames and can send commands.  The session is closed only when
    the last client disconnects.
    """
    global _shared_session, _session_semaphore, _shared_lock
    conn_id = id(websocket)
    is_session_creator = False

    # Get client IP for rate limiting
    client_ip = "unknown"
    try:
        if hasattr(websocket, 'remote_address') and websocket.remote_address:
            client_ip = str(websocket.remote_address[0])
    except Exception:
        pass

    logger.info(f"New connection: {conn_id} from {client_ip}")

    # Check rate limit
    allowed, reason = _check_rate_limit(client_ip)
    if not allowed:
        logger.warning(f"Rate limited connection from {client_ip}: {reason}")
        try:
            await websocket.send(json.dumps(make_error_response(
                ErrorCode.CONNECTION_ERROR,
                "Rate limited",
                reason
            )))
            await websocket.close(CloseCode.RATE_LIMITED, reason)
        except Exception:
            pass
        return

    # ------------------------------------------------------------------
    # Join or create the shared session
    # ------------------------------------------------------------------
    async with _shared_lock:
        session = _shared_session
        if session is None:
            # First client — create a new browser session
            session = BrowserSession("shared")
            try:
                await session.start()
            except Exception as e:
                logger.error(f"Browser launch failed: {e}")
                _record_attempt(client_ip, False)
                try:
                    await websocket.send(json.dumps(make_error_response(
                        ErrorCode.BROWSER_LAUNCH_FAILED,
                        "Failed to launch browser",
                        str(e)
                    )))
                    await websocket.close(CloseCode.BROWSER_LAUNCH_FAILED, "Browser launch failed")
                except Exception:
                    pass
                return

            _shared_session = session
            active_sessions[conn_id] = session
            is_session_creator = True
            logger.info("Shared browser session created")

            # Frame sender that broadcasts to ALL connected clients
            async def send_frame_to_all(frame_data: bytes):
                for ws in list(_shared_clients):
                    try:
                        await ws.send(frame_data)
                    except websockets.exceptions.ConnectionClosed:
                        pass
                    except Exception as e:
                        logger.debug(f"Frame broadcast error: {e}")

            try:
                await session.start_screencast(send_frame_to_all)
            except Exception as e:
                logger.error(f"Screencast start failed: {e}")
                try:
                    await session.close()
                except Exception:
                    pass
                _shared_session = None
                try:
                    await websocket.send(json.dumps(make_error_response(
                        ErrorCode.SCREENCAST_FAILED,
                        "Failed to start screencast",
                        str(e)
                    )))
                    await websocket.close(CloseCode.SCREENCAST_FAILED, "Screencast failed")
                except Exception:
                    pass
                return
        else:
            logger.info(f"Client {conn_id} joining existing shared session")

        # Register this websocket as a client of the shared session
        _shared_clients.add(websocket)

    _record_attempt(client_ip, True)

    # Send initial state to the newly connected client
    try:
        await websocket.send(json.dumps({
            "type": "connected",
            "url": await session.get_current_url(),
            "title": await session.get_page_title(),
        }))
    except Exception as e:
        logger.error(f"Failed to send initial state: {e}")
        async with _shared_lock:
            _shared_clients.discard(websocket)
        return

    # Navigation event types that need URL/title response
    NAV_TYPES = {"goto", "goBack", "goForward", "reload", "back", "forward"}

    # ------------------------------------------------------------------
    # Message loop
    # ------------------------------------------------------------------
    try:
        async for raw_message in websocket:
            try:
                msg = json.loads(raw_message)
                msg_type = msg.get("type")
                if msg_type != "mouse_move":
                    logger.debug(f"Received message: {msg_type}")

                # Ping/pong — reply only to the sender
                if msg_type == "ping":
                    try:
                        await websocket.send(json.dumps({
                            "type": "pong",
                            "ts": msg.get("ts", 0),
                        }))
                    except Exception:
                        pass
                    continue

                # Agent action — broadcast to ALL other clients (for co-browsing overlay)
                if msg_type == "agent_action":
                    await _broadcast_json(msg, exclude=websocket)
                    # Also echo back to sender for confirmation
                    try:
                        await websocket.send(json.dumps(msg))
                    except Exception:
                        pass
                    continue

                # Navigation types — process and broadcast result to ALL clients
                if msg_type in NAV_TYPES:
                    if msg_type == "goto" and msg.get("url"):
                        navigating_msg = {"type": "navigating", "url": msg.get("url")}
                        await _broadcast_json(navigating_msg)

                    error = await session.handle_input(msg)
                    if error:
                        if "_req_id" in msg:
                            error["_req_id"] = msg["_req_id"]
                        await websocket.send(json.dumps(error))
                    else:
                        resp = {
                            "type": "navigated",
                            "url": await session.get_current_url(),
                            "title": await session.get_page_title(),
                            "canGoBack": session.can_go_back,
                            "canGoForward": session.can_go_forward,
                        }
                        if "_req_id" in msg:
                            resp["_req_id"] = msg["_req_id"]
                        # Send navigated to ALL clients so UI stays in sync
                        await _broadcast_json(resp)
                else:
                    result = await session.handle_input(msg)
                    if result:
                        if "_req_id" in msg:
                            result["_req_id"] = msg["_req_id"]
                        # Responses like screenshot_result go to the requesting client
                        await websocket.send(json.dumps(result))

            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON message: {e}")
                try:
                    await websocket.send(json.dumps(make_error_response(
                        ErrorCode.INVALID_MESSAGE,
                        "Invalid JSON message",
                        str(e)
                    )))
                except Exception:
                    pass
            except websockets.exceptions.ConnectionClosed:
                logger.debug("Connection closed during message handling")
                break
            except Exception as e:
                logger.error(f"Message processing error: {e}")

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Connection closed: {conn_id}")
    except Exception as e:
        logger.error(f"Session error for {conn_id}: {e}")
        try:
            await websocket.send(json.dumps(make_error_response(
                ErrorCode.CONNECTION_ERROR,
                "Session error",
                str(e)
            )))
        except Exception:
            pass
    finally:
        # Remove this client from the shared set
        async with _shared_lock:
            _shared_clients.discard(websocket)
            remaining = len(_shared_clients)
            logger.info(f"Client {conn_id} disconnected ({remaining} client(s) remaining)")

            # Only close the session when the LAST client disconnects
            if remaining == 0 and _shared_session is not None:
                logger.info("Last client disconnected — closing shared session")
                try:
                    await _shared_session.close()
                except Exception as e:
                    logger.error(f"Session cleanup error: {e}")
                _shared_session = None
                active_sessions.clear()
            elif conn_id in active_sessions:
                del active_sessions[conn_id]


def check_browsers_installed():
    """Check if Playwright browsers are installed, install if not."""
    # Quick check: see if playwright browser path exists
    browser_path = os.path.expanduser("~/.cache/ms-playwright") if sys.platform != "win32" else os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
    if not os.path.exists(browser_path) or not os.listdir(browser_path):
        logger.info("Playwright browsers not found, installing...")
        install_playwright_browsers()
        return True
    return False


async def cleanup_all_sessions():
    """Clean up all active browser sessions."""
    logger.info(f"Cleaning up {len(active_sessions)} active session(s)...")
    cleanup_tasks = []
    for session_id, session in list(active_sessions.items()):
        cleanup_tasks.append(session.close())
    if cleanup_tasks:
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)
    active_sessions.clear()

    # Shutdown shared Playwright instance
    await shutdown_playwright()

    logger.info("All sessions cleaned up")


async def main():
    """Start the WebSocket server with graceful shutdown support."""
    global _shutdown_event, _session_semaphore, _shared_lock
    _shutdown_event = asyncio.Event()
    _session_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SESSIONS)
    _shared_lock = asyncio.Lock()

    # Pre-check browsers on startup
    check_browsers_installed()

    logger.info(f"Starting server on ws://localhost:{WS_PORT}")
    logger.info(f"Max concurrent sessions: {MAX_CONCURRENT_SESSIONS}")
    if DEBUG_MODE:
        logger.info("Debug mode enabled - verbose logging active")
    if STEALTH_MODE:
        logger.info("Stealth mode enabled - anti-bot evasion active")

    # Set up signal handlers for graceful shutdown
    if sys.platform != "win32":
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: _shutdown_event.set())
    else:
        # Windows: use signal module directly for SIGINT (Ctrl+C)
        def _win_shutdown(signum, frame):
            _shutdown_event.set()
        signal.signal(signal.SIGINT, _win_shutdown)
        try:
            signal.signal(signal.SIGTERM, _win_shutdown)
        except (OSError, ValueError):
            pass  # SIGTERM may not be available on Windows

    # Allow binding to all interfaces for container/network access
    bind_host = os.environ.get("BROWSER_WS_HOST", "0.0.0.0")

    # Disable permessage-deflate (JPEG doesn't compress well and compression adds latency/CPU).
    # Increase max_size to tolerate larger frames on bigger viewports.
    # Enable WebSocket-level ping/pong keepalive (20s interval, 20s timeout).
    try:
        async with serve(
            handle_connection,
            bind_host,
            WS_PORT,
            compression=None,
            max_size=8 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
        ):
            logger.info(f"Server started successfully on {bind_host}:{WS_PORT}")
            # Wait for shutdown signal
            if sys.platform != "win32":
                await _shutdown_event.wait()
            else:
                # On Windows, handle Ctrl+C gracefully
                try:
                    await _shutdown_event.wait()
                except asyncio.CancelledError:
                    pass
    except OSError as e:
        if "address already in use" in str(e).lower() or e.errno == 10048:  # 10048 is Windows WSAEADDRINUSE
            logger.error(f"Port {WS_PORT} is already in use. Stop the other server or use a different port.")
            logger.error("Set BROWSER_WS_PORT environment variable to use a different port.")
        else:
            logger.error(f"Server startup failed: {e}")
        return
    except Exception as e:
        logger.error(f"Server error: {e}")
        return
    finally:
        # Graceful shutdown: clean up all sessions
        await cleanup_all_sessions()
        logger.info("Server shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
