/**
 * SkinSense — Global App Initialization v2.0
 * Fixes:
 *  - Proper load-order: checks health, then Auth.init() handles session check
 *  - System status badge update from /api/health
 *  - Global debounce helper (used by multiple modules)
 *  - Exposes global navigateTo helper (also in sidebar.js)
 *  - Chat quick-message helper (also in sidebar.js)
 */

// ── System Health Check ──
async function checkSystemStatus() {
    const badge      = document.getElementById('system-status-badge');
    const statusText = document.getElementById('system-status-text');
    if (!badge || !statusText) return;

    try {
        const res  = await fetch('/api/health');
        const data = await res.json();
        const ok   = data.status === 'healthy' || data.model_available;
        badge.classList.toggle('offline', !ok);
        statusText.textContent = ok ? (data.system_status_text || 'System Ready') : 'System Offline';
    } catch (err) {
        badge.classList.add('offline');
        statusText.textContent = 'Connection Error';
    }
}

// ── Bootstrap Tab Switching Helper ──
function switchTab(paneId) {
    const targetPane = document.getElementById(paneId);
    if (!targetPane) return;
    const tabBtn = document.querySelector(`[data-bs-target="#${paneId}"]`);
    if (tabBtn) {
        const bsTab = bootstrap.Tab.getOrCreateInstance(tabBtn);
        bsTab.show();
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Global debounce (used by history, education, etc.) ──
if (typeof window.debounce !== 'function') {
    window.debounce = function (fn, ms) {
        let timer;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), ms);
        };
    };
}

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
    checkSystemStatus();
    // Note: Auth.init() is called by auth.js, which triggers Navigation.showAppShell/showAuthScreen
    // Navigation.init() is called by sidebar.js
    // All section modules init themselves and register SectionHooks
});
