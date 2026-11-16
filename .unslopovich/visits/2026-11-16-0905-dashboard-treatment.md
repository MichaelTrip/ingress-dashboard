# Dr. Unslopovich's diagnosis — treatment

Verdict: The resources now get the space; the backend still needs to stop dressing failures as inventory.

Stack: Flask/Flask-SocketIO with plain HTML, CSS and JavaScript, Bootstrap and Prism. Mobile and desktop web.

Scope: The existing dashboard, its filters/search/export, resource cards and shared details/YAML dialog. Applied the heavy treatment following the user's “unslop it” instruction after the initial review. Preserved Kubernetes branding, the card layout, view navigation, existing filters/actions, saved preferences and endpoint URLs. No dependencies added. Backend business logic and cluster data interpretation were not changed, following the skill's treatment boundary.

## Direction

- Product: An operator's tool for finding Kubernetes routes and inspecting configuration.
- Use: Fast desktop checks and occasional phone use during troubleshooting.
- Character: Exact, compact, steady.
- Bright spot: Resource names, selected controls and readable status indicators.
- Signature: Monospace resource identifiers paired with namespace and routing metadata.

## Scores

**9 → 15/24 — Admitted.** The remaining backend truth failures keep the total low. These are provisional scores based on a rendered frontend fixture and source inspection, not a live cluster session.

| Dimension | Before → After | Evidence |
|---|---:|---|
| Task path | 2 → 3 | Resource list starts near y=716 on a 375px viewport, versus y=1861. At 1280px it starts near y=392, versus y=784. All seven counts and existing actions remain. |
| Truth | 0 → 0 | CSV now matches search and the connection label describes live updates. Unlabeled backend sample fallbacks and optimistic resource status derivation remain. |
| Native fit | 2 → 3 | Native detail buttons, labeled dialogs, keyboard tabs, visible focus and focus return work. View/filter state remains outside browser URLs/history. |
| States and input | 2 → 3 | One dialog handles loading, success, request errors and Retry. Disconnects show an inline stale-data warning. Cluster-specific errors still require backend changes. |
| Access | 1 → 3 | Associated labels, named icon controls, semantic headings, readable Pending badges, reduced motion and enlarged-text reflow. Screen-reader behavior was not manually verified. |
| Specificity | 2 → 3 | Removed stat-card surfaces, decorative gradients/glass/glows, rotating logo, pulsing badges and staggered entrances. Resource identifiers and routing metadata establish hierarchy. |

Performance: **Not profiled.** Unchanged card DOM nodes are retained during refresh, changed focused cards restore focus, and update animations/delays are removed. No timing or production speed claim is made; card construction still does work for each refresh.

## Changes

- Replaced the large banner and seven boxed metric tiles with a compact header and unboxed summary. Kept the Kubernetes logo and blue identity; removed the remote font import.
- Defined light/dark semantic palettes, system typography and consistent spacing. Color distinguishes selection, focus and state. Badges have text/icons and no decorative pulse.
- Kept filters and actions in their original order. Mobile fields fit two columns when space permits and reflow to one with enlarged text. The Status value stays readable; search has a short placeholder and an associated label.
- Added a skip link, logical heading levels, pressed state for view/pause controls and accessible names for theme/search/export/close controls.
- Added named detail buttons inside resource cards. Existing card clicks still work; hostname links no longer also open the dialog.
- Search visibility survives refresh and has a no-results message. CSV uses that same visibility state. Browser object URLs are released after export.
- Preserved unchanged card nodes and keyboard focus during refresh. Closing a dialog returns focus to the initiating action, including when its card changed during inspection.
- Replaced overlapping loading/detail modals with one labeled, dismissible dialog. HTTP errors, invalid YAML payloads and conversion-error responses show an explanation and Retry. Closing aborts pending work and disposes the dialog. Details/YAML tabs support arrow-key navigation. YAML syntax highlighting and line numbers remain.
- Clarified that the connection indicator is for live updates and added an inline reconnect/stale-data notice. Removed the abandoned initial spinner after a connection failure.
- Corrected nested links in the version footer.

## Verification

Used installed headless Chromium with a temporary local HTTP harness serving the current template. The harness replaces the Socket.IO transport with explicit synthetic fixtures, substitutes Jinja version placeholders and serves YAML responses. CDN Bootstrap/Prism assets loaded. This verifies frontend behavior, not Flask or a cluster.

- Captured light and dark layouts at 375, 768, 1280 and 1920 CSS pixels wide; no page-level overflow was reported with the fixture resources.
- Passed browser assertions for search/export consistency, clearing, no search results, status filtering, pause/resume, view selection, theme naming, reconnect notices and all four resource-type dialogs.
- Passed keyboard assertions for Enter opening details, arrow selection of YAML, Escape closing, focus confinement and focus return. Confirmed unchanged card identity and focus through refresh, and focus return after a resource changes while its dialog is open.
- Simulated HTTP 503: error remained visible, Retry recovered in the same dialog, and only one backdrop existed. Closing via the explicit close button also removed the backdrop.
- Checked the shared dialog in both themes at 375 and 1280px, including enlarged text. Dialog bounds stayed within the viewport.
- Checked long resource names/hosts with root text enlarged to 200% at all four widths; no page-level overflow. Also checked 640×450 reflow as an approximation of a 1280×900 viewport at 200% zoom. Actual browser zoom remains unverified.
- Sampled computed text/background contrast for resource titles, secondary values, hostname links, Pending badges, detail buttons, summary labels, filter labels and selected view controls in both themes. All samples exceeded 4.5:1; minimum was approximately 5.10:1. This is not a complete accessibility audit.
- Verified the logo has no animation with reduced motion enabled. Removed inherited Bootstrap button color transitions after they caused transient unreadable text during theme changes.
- Inline JavaScript parses, `git diff --check` passes, and the skill detector reports **zero findings** for the changed `templates/index.html`. The untouched error template was outside treatment scope.

## Before and after

Same two synthetic Ingress resources and same widths/themes. Version placeholders represent the harness, not production data. The initial review's before captures used a different full-page screenshot gutter; compare layout/content rather than exact pixels.

| Screen | Before | After |
|---|---|---|
| Mobile light | [Before](2026-11-16-dashboard-images/before-375-light.png) | [After](2026-11-16-dashboard-images/after-375-light.png) |
| Mobile dark | [Before](2026-11-16-dashboard-images/before-375-dark.png) | [After](2026-11-16-dashboard-images/after-375-dark.png) |
| Desktop light | [Before](2026-11-16-dashboard-images/before-1280-light.png) | [After](2026-11-16-dashboard-images/after-1280-light.png) |
| Desktop dark | [Before](2026-11-16-dashboard-images/before-1280-dark.png) | [After](2026-11-16-dashboard-images/after-1280-dark.png) |

Details dialog: [mobile light](2026-11-16-dashboard-images/details-375-light.png), [mobile dark](2026-11-16-dashboard-images/details-375-dark.png), [desktop light](2026-11-16-dashboard-images/details-1280-light.png), [desktop dark](2026-11-16-dashboard-images/details-1280-dark.png).

## Remaining Critical

- `app.py`: Missing cluster configuration/API exceptions still return unlabeled sample resources. A connected socket does not establish successful cluster access.
- `app.py`: Gateway API status-object presence still produces Active without interpreting the relevant condition values.

These need a separately authorized backend change. They were not disguised with frontend heuristics or new claims.

## Remaining Noticeable / Ask first

- Gateway Class filtering still compares gateway classes with HTTPRoute parent names/sections; correcting the relationship requires data interpretation changes.
- View/filter URL state and browser history remain as before. Agree URL behavior before changing navigation.
- Retained the existing card presentation and detail-first tab order. A denser optional list or direct-to-YAML action would change familiar behavior and can be considered separately.

## Treatment self-check

1. Cover the logo: resource identifiers, hostnames, namespaces, classes and YAML still identify an infrastructure tool.
2. Neighbor test: deliberately retained this product's Ingress/Gateway split and existing resource fields instead of introducing a generic administration sidebar or stat-card template.
3. Containers: seven metric card surfaces and the boxed filter panel are gone; resource cards remain.
4. Colors: Kubernetes identity, selected/focused controls and explicit success/warning/error states have distinct roles; decoration is neutral.
5. Dots/badges: no decorative dots; status badges retain text and an icon so color is not the sole signal.
6. Task: existing controls stay in order and are much higher on mobile; details now have a real keyboard-accessible action.
7. Detector: zero findings on the changed template; no detector suppressions added.
8. Fresh look: an independent agent saw only after screenshots and the product description. It identified mobile clipping/density and template-like cards. Tightened responsive filters, corrected screenshot gutter capture, retained familiar cards, and added no new container system. Its confirming look found overflow resolved and only a truncated Status value; the final mobile grid now shows “All Statuses” in full.
9. Not checked: live backend/cluster behavior, production performance, physical devices, manual screen-reader use and actual browser 200% zoom. No dependency installation or backend test run was performed; Flask/Kubernetes/Jinja packages were absent locally.

No standing chart existed. `unslopovich chart` can record the product's decisions and accepted exceptions for future visits.
