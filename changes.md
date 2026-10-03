# JyotishAI UI Refactoring Log

This document tracks all the design-focused UI/UX enhancements made to the JyotishAI frontend. 
**Core Rule:** Functionality and data integrity remain 100% untouched.

## Phase 1: Environment & Profile Creation
- **Environment Setup:** Bypassed Netlify plugin errors locally by running Vite with `VITE_DISABLE_NETLIFY=true`.
- **Login Page Enhancement:** Added a sleek password visibility toggle (Eye icon) to the login form.
- **Profile List Redesign:** Refactored the "Your Profiles" dashboard to remove bulky outer cards in favor of a cleaner, left-aligned, premium grid layout.
- **Step-by-Step Profile Wizard:** Converted the multi-column profile creation form into an elegant 3-step wizard.
  - Implemented a top connecting progress bar with step indicators.
  - Added a "Show Advanced Settings" toggle to hide complex astronomical inputs (Latitude, Longitude, Ayanamsa, etc.) by default.
  - Redesigned "Back" and "Next" buttons with premium outline and gold hover effects.
- **Layout Alignment:** Adjusted the max-width containers (`max-w-6xl` vs `max-w-3xl`) so that navigation buttons precisely align to the left edge of the dashboard.

## Phase 2: Education & Career Reports (UG Page)
- **Full Width Alerts:** Removed artificial width constraints (`max-w-xl`) from the "Avoid As Primary" alerts in the UG Evidence report to allow full-width stretching.
- **Vertical Timeline Redesign (Academic Execution Path):** 
  - Completely replaced the old horizontal text-based flowchart with a modern Vertical Stepper Timeline (similar to Swiggy/GitHub trackers).
  - Used connecting vertical borders, conditional gold dots, and moved the "Very Strong / Strong" labels into premium uppercase top-right corner badges.
  - Added micro-animations (`hover:-translate-y-0.5`, `hover:shadow-md`).
- **Sticky Tabs Bar:** Made the "Overview | Top fields | Evidence" report tabs sticky (`top-[72px]`) while scrolling, utilizing a glassmorphism backdrop blur (`backdrop-blur-xl bg-muted/90`).
- **Smooth Tab Navigation:** Attached an `onValueChange` event to the Tabs component to auto-scroll the window back to the top (`window.scrollTo`) when switching between report tabs, preventing users from being stranded halfway down the page.

### 2b. PUC Stream Report Design Alignment
- **Narrative Styling:** 
  - Restyled the AI Narrative section to seamlessly match the UG report format by using the premium `SectionTitle` component with a status chip.
  - Upgraded the "Student Narrative" block with a subtle primary-tinted background (`bg-primary/8`) and a bold gold left border (`border-l-4 border-gold`).
- **Technical De-cluttering:** 
  - Wrapped the dense "Astrological Reasoning" bullet points inside a clean, collapsible `Accordion` featuring a `🔭` icon, keeping the default view focused purely on the student's actionable advice.
  - Replaced standard HTML bullet points with elegant gold dots (`• text-gold`) for list items.
- **Grid Cleanup:** 
  - Removed legacy hardcoded borders (`border-b`, `border-r`) from the top `StatTile` metric grid, allowing it to breathe and match the cleaner layout of the UG executive summary.
## Phase 3: Authentication Flow
- **Dashboard Visibility:** Updated `AuthGate.tsx` to instantly redirect unauthenticated users to the `/login` route using `@tanstack/react-router`'s `<Navigate>`. This replaces the previous behavior where unauthenticated users would still see the full dashboard sidebar/header with an inline "Login required" message.
- **FOUC (Flash of Unauthenticated Content) Fix:** Swapped the nesting order of `AppShell` and `AuthGate` in `__root.tsx` so that `AuthGate` intercepts the render *before* the dashboard shell mounts, completely eliminating the split-second "dashboard flash" when hitting `/` logged out.
- **Premium Login Page Redesign:** 
  - Added a deep cosmic/astrological background to `AuthLayout` using a gold radial gradient and ambient blur elements.
  - Upgraded the login `<Card>` with a glassmorphism effect (`backdrop-blur-2xl bg-card/60`), soft inner shadows, and a clean centered layout.
  - Enhanced input fields with muted backgrounds and gold focus rings.
  - Improved the "Sign in" button with a premium gradient, drop shadow, and a smooth lift animation on hover (`hover:-translate-y-0.5`).

## Phase 4: Career Timeline Report
- **Header Alignment (UG-style):** Removed the dark premium banner and replaced it with a clean, minimalistic centered layout that perfectly matches the UG Report aesthetic.
  - Centered the title and birth details cleanly without backgrounds.
  - Re-styled the metadata tags as light, subtle pills (`bg-muted/40 text-muted-foreground`).
  - Integrated the overall confidence metric inline with the tags, keeping the pulsing green dot for engine vitality without overwhelming the visual hierarchy.

- **Career Roadmap Card Refinements:**
  - Added a dynamic `hover:shadow-lg` and `hover:border-gold/40` state to the roadmap period cards to make them feel interactive and premium.
  - Introduced a conditional left-border accent (`border-l-[4px] border-l-gold`) specifically for the active "Current" career period.
  - Enhanced the "Current" badge with a gold tinted glass background, glowing shadow, and a real-time pulsing indicator dot.
  - Added an elegant `Sparkles` icon and soft highlight backgrounds to the "In Plain Language" narrative section.
  - **Technical Data De-cluttering:** Moved all highly technical astrological data (Astrological Explanation, KP overrides, Yogas, D10 tables, Contradiction checks) into a new sleek `🔭 View Astrological Evidence` accordion. This keeps the cards incredibly clean for laypersons while keeping the technical evidence just one click away. Elevated the "Family Guidance" section to be visible outside the accordion.

- **Executive Summary Layout Reorganization:**
  - Consolidated the "Outcome Strength" table and the core executive metrics (Primary Opportunity, Peak Dasha Lord, etc.) into a cohesive side-by-side layout (`grid-cols-[1.3fr_1fr]`) on larger screens.
  - Refined the executive metrics into a sleek 1-column row-wise layout (vertical stack). To optimize space, the label and value inside each row are distributed horizontally (left/right aligned), eliminating the awkward vertical whitespace caused by the previous 2x2 square grid.
- **Sticky Tabs Navigation Refactoring:**
  - Completely replaced the disjointed left-sidebar/right-content dual-scroll layout with a clean, unified Tabbed layout (matching the UG Report).
  - Implemented sticky Tabs (`top-[80px]`) that act as an elegant floating pill (`backdrop-blur-2xl bg-muted/95 shadow-lg`), eliminating the previous full-width rectangular background cut-off issue.
  - Engineered precise auto-scroll logic that snaps smoothly to the Tabs container (instead of the absolute page top) when switching views, drastically improving mobile responsiveness and reading continuity.

- **Micro-timing Text Overflow Fix:**
  - Fixed a visual bug in the "SHOULD I...? — SCENARIO ADVICE" cards where long sentences (opportunity and risk factors) were cutting through the container.
  - Replaced the restrictive single-line `Tag` component with flexible, multi-line alert boxes (featuring `+` and `−` indicators) that gracefully wrap text without breaking the layout.
- **Data De-cluttering & Content Separation:**
  - Split the bottom supplementary sections into two distinct modules: Actionable vs. Technical.
  - Kept highly actionable tools (`Micro-timing` and `Foreign Opportunity windows`) directly on the **Career Roadmap** tab.
  - Shifted all heavy astrological data visualizations (`Career Trajectory Chart`, `Year-by-year Calendar`, and `Mahadasha Arcs`) exclusively to the **Astro Insights** tab.
  - Wrapped all residual astrological reasoning (e.g., "Moon transits H6") within the actionable components into subtle `🔭 Astro Logic` accordions to ensure the UI remains 100% action-focused for laypersons.
- **Astro Insights Dashboard Layout:** Expanded the `Astro Insights` tab container width (`max-w-5xl`) and refactored the legacy sidebar content (Snapshot, D10, KP) into a sleek multi-column grid (`grid-cols-1 md:grid-cols-2`). This fixes the awkward narrow vertical stacking, and gives the full-width data charts (`Trajectory`, `Calendar`) maximum horizontal space.

---
*Future changes will be appended here.*

## 3. Business Module UI/UX Upgrade (Sync with Career & UG)
- **Design System Overhaul:** 
  - Completely removed the legacy `business-report.css` and hardcoded `biz-*` classes.
  - Replaced the entire layout with the premium, Tailwind-based `shadcn/ui` components (`Panel`, `SectionTitle`, `Tag`, `Tabs`, `Accordion`).
  - Added glassmorphic backgrounds (`backdrop-blur-xl`, `bg-muted/95`), responsive grids, and subtle entry animations (`animate-rise`, `fade-in-50`).
- **Data De-cluttering & Content Separation:**
  - Removed the outdated `Profile vs Astrologer` toggle switch.
  - Re-architected the page into two clear tabs: **Business Roadmap** (Actionable) and **Astro Insights** (Technical evidence).
  - **Business Roadmap:** Houses the Final Verdict, Transition Timing, Recommendation, Financial Readiness, top 12 Sectors, and Favorable Timed Windows. All supporting astrological jargon within Timed Windows was wrapped in `🔭 Astro Logic` accordions.
  - **Astro Insights:** A dedicated dashboard for Structural Promise Fields (KPI scorecards), full list of sectors, Significator charts, and the Technical Appendix (Muhurta, Ashtakavarga, Yogas, D2 Hora, etc.). 
  - *Result:* The Business page now looks identical in aesthetic and premium feel to the Career and UG reports, maintaining the strict rule of "No data hide or delete, no functionality change."

### 3b. Business Module — Iterative Refinements
- **Data Parity Restoration (User-Side — Business Roadmap Tab):**
  - Re-added **"Your Strongest Years for Business" (Ashtakavarga)** section that was missing from the user-facing tab.
  - Re-added **"Special Combinations in Your Chart" (Yogas)** with status indicator.
  - Re-added **"Dispute & Contract Caution Points"** with `legal_dispute_risk_status` and evidence list.
  - Re-added **"Wealth Flow Indicators (D2 Hora)"** with flex-wrap card grid for individual evidence items.
  - All four sections are now rendered inside bordered card containers (`bg-card border rounded-xl shadow-sm`) with titles **inside** the box for visual consistency.

- **Data Parity Restoration (Astrologer-Side — Astro Insights Tab):**
  - Re-added **"Capital Strategy: Bootstrap vs External Capital"** panel showing `operating_model.best_fit` and note.
  - Re-added **"Forecast Window & Timing Status"** panel showing `forecast_metadata` (as_of, years_ahead, status, periods).
  - Both sections positioned directly below the **Structural Promise Fields** KPI scorecards.
  - Titles moved **inside** card containers (not floating above) per user feedback.
  - **"Dispute & Contract Risks"** section made unconditionally visible (removed the `asArray().length > 0` guard) so the empty state ("No items recorded.") is always shown for audit transparency.
  - **"Signal Reconciliation"** and **"Contradiction findings"** moved to the top of the Astro Insights tab for astrologer audit priority.

- **Layout Fixes:**
  - Changed Business Insights lower half from **side-by-side** (`grid-cols-2`) to **vertical stacking** (`flex-col`) per user request — all sections now render one-by-one top to bottom.
  - Fixed **"Contradiction findings"** heading color from purple (`text-royal`) to black (`text-foreground`).

- **Timed Windows Label Colors:**
  - Fixed the `badgeClass` → `Tone` mapping bug where FAVORABLE/STRONG_FAVORABLE labels were always falling through to gray ("muted").
  - Now correctly maps: `FAVORABLE` / `STRONG_FAVORABLE` → **green** (`success`), `CAUTION` → **orange** (`warn`), `MIXED` → **gray** (`muted`).

## Phase 5: Sidebar Session Gating (Overall App Flow)
- **Problem:** After login, all sidebar links (Charts, KP, Business, etc.) were immediately clickable even without an active profile/session, leading users to empty "Open a profile first" screens.
- **Solution (Option A — Disable until session active):**
  - Added `needsSession: true` flag to all NAV items in the **Systems** and **Intelligence** groups.
  - Added a `SESSION_REQUIRED_GROUPS` set for group-level checks.
  - When `useChartSession()` returns no `birthInput`, these sidebar links render as **grayed-out `<span>` elements** (`opacity-40`, `cursor-not-allowed`) instead of clickable `<Link>` components.
  - Hover tooltip: "Open a profile first".
  - Education Analysis child links (PUC/UG) are hidden when parent group is disabled.
  - **Always-accessible links:** Profiles, Panchanga, AI Assistant, Prashna, Reports, Settings remain clickable regardless of session state.
  - Applied to both **desktop sidebar** and **mobile drawer**.
  - **Zero existing code deleted** — only added disabled rendering branch alongside existing Link rendering.

## Phase 6: Global Consistency & TypeScript Hardening
- **Master Shell Alignment:** 
  - Standardized all report containers (Business, Job Timeline, Education) to use the `ReportShell`'s `max-w-[1180px]` constraint. 
  - Stripped out redundant internal horizontal padding (`px-4`, `md:px-5`, etc.) from nested section wrappers to prevent double-padding and perfectly align margins across all modules (UG, PUC, Business, Career).
- **Refresh Action Refactoring:** 
  - Extracted the "Refresh" buttons from deep inside the report body in `BusinessSection` and `CareerTimelineSection`.
  - Shifted them globally up into the `PageHeader` using the `titleAction` prop so the refresh icon appears elegantly inline with the page title, identical to the Education modules.
- **PageHeader Separator:** 
  - Added a global subtle bottom border (`border-b border-border pb-5`) to `PageHeader` in `AppShell` to clearly separate titles from the body content.
  - Increased the subtitle width constraint from `max-w-2xl` to `max-w-4xl` to ensure long descriptions render on a single line on desktop screens.
- **Favicon Integration:** 
  - Added the user's custom gold star icon as a global `favicon.png`, registering it directly in the TanStack Start root meta links.
- **ProfileWizard Active State Highlighting:** 
  - Introduced a clear visual active state for the "Your Profiles" grid. The currently loaded profile now features a gold border, subtle gold background highlight, and a distinct "ACTIVE" micro-badge next to the name.
  - Enhanced UX by morphing the "Open Analysis" button into a solid gold "View Charts" button when the profile is already active.
- **TypeScript Strict Compliance:** 
  - Executed a comprehensive type-check (`tsc --noEmit`) and resolved all strict type mismatch errors, explicitly handling `undefined` rendering bugs and correcting overlapping index signatures via `unknown` typecasting across components (`PucStreamReport`, `ProfileWizard`, `ProfileConfirmReport`, `hydrate.ts`, and `CareerTimelineSection`).
