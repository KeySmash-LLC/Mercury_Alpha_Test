/**
 * PostHog init — runs after posthog-bundle.js has defined window.posthog.
 * No CDN loading, no <script> tag injection — fully self-contained so it works
 * on pages with Trusted Types policies (e.g. LinkedIn).
 *
 * IMPORTANT: addInitScript runs in ALL frames (including about:blank iframes).
 * We must guard against iframe execution to avoid:
 * - SecurityErrors on opaque-origin frames (can't access cookies)
 * - Duplicate PostHog instances that corrupt session recording data
 * - Broken sessions showing "all inactivity" in the PostHog dashboard
 */
if (window.self === window.top) {
    posthog.init('phc_wVt5tCcjb58xQNqMTzdJ7E3i5j8XEWLdSvvQu2mjX5f', {
        api_host: 'https://us.i.posthog.com',
        person_profiles: 'identified_only',
        autocapture: false,
        session_recording: {
            maskAllInputs: true,
            maskInputOptions: { password: true },
            maskTextSelector: ''
        },
        loaded: function(ph) {
            // Use the same distinct_id as server-side pipeline events so PostHog
            // can link session replays to scout_complete / pipeline_complete events.
            // window.__PH_DISTINCT_ID is injected by start-playwright-mux.sh from .env.
            var distinctId = window.__PH_DISTINCT_ID || 'scout-agent';
            var userName = window.__PH_USER_NAME || '';
            var personProps = {};
            if (userName) personProps.name = userName;
            ph.identify(distinctId, personProps);

            // Force-start session recording without waiting for /decide API call.
            // The /decide call can be blocked by CSP on strict sites (LinkedIn, etc.),
            // which would silently prevent rrweb from starting.
            ph.startSessionRecording();

            // Playwright automation doesn't fire mouse/keyboard events that rrweb
            // recognises as "user activity." Without these, PostHog's session player
            // treats the entire recording as inactivity and fast-forwards through it.
            // Dispatch a synthetic mousemove every 5s to keep rrweb marking the
            // session as active. The coordinates are off-screen so it won't interfere
            // with actual page interaction.
            setInterval(function() {
                try {
                    document.dispatchEvent(new MouseEvent('mousemove', {
                        bubbles: true, clientX: -1, clientY: -1
                    }));
                } catch(e) {}
            }, 5000);

            ph.capture('posthog_init_success', {
                url: window.location.href,
                recording_started: ph.sessionRecordingStarted()
            });
            console.log('[PostHog] init OK — recording:', ph.sessionRecordingStarted(), 'distinct:', distinctId, window.location.href);
        }
    });
}
