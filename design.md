# Design System Strategy: Lelong Analytical Ledger (The Quantitative Authority)

This design system is engineered for high-stakes property auction analytics. We have moved away from the "generic SaaS dashboard" aesthetic toward a high-density, "financial terminal" approach that prioritizes data throughput and professional-grade utility over white space.

## 1. Creative North Star: "The Data Terminal"
The goal is to provide investors with a sense of "Information Dominance." Every pixel should serve a functional purpose. The interface should feel like a high-precision instrument—efficient, authoritative, and unsentimental.

## 2. Visual Language & Foundation

### Typography (Authority & Precision)
- **Primary Font:** **Manrope** (Selected for its geometric clarity and excellent readability at small sizes).
- **Hierarchy:**
    - **Data Points:** Bold, high-contrast black/dark-blue for primary metrics (Yield, Market Gap, Price).
    - **Labels:** Semi-bold, muted slate for secondary metadata to reduce visual noise.
    - **Headlines:** Tight tracking, condensed where possible to maximize vertical space.

### Color Palette (The Professional Spectrum)
- **Primary:** `#1B365D` (Deep Navy) – Represents stability, institutional trust, and analytical rigor.
- **Surface:** `#F7F9FB` (Cool Gray) – Minimizes eye strain during long analysis sessions.
- **Accents (Semantic Clarity):**
    - **Success/Gain:** Emergent green for positive yield or price gaps.
    - **Alert/Urgency:** Sharp red for high-competition or tight auction dates.
    - **Focus:** Muted blue for interactive elements and filters.

### Geometry (The Grid)
- **Roundness:** `ROUND_FOUR` (Minimal rounding). Soft enough to feel modern, but sharp enough to maintain a technical edge.
- **Density:** Tight padding (4px-8px standard) to maximize information per screen.

## 3. Core Analytical Components

### High-Density Cards
- **Logic:** Every listing card must display at least 4 key metrics (Price, Gap, Yield, Date) without requiring a tap.
- **Visuals:** Borderless containers with subtle background shifts to differentiate rows.

### Performance Indicators
- **Trend Charts:** Sparklines and simplified bar charts integrated directly into dashboards to show volume and success rates at a glance.
- **Heatmaps:** Strategic use of color scales to indicate market saturation or "Hot" areas.

## 4. Interaction Model
- **Mobile-First Utility:** Sticky headers/filters and bottom navigation for one-handed operation.
- **Scan-to-Deep-Dive:** A clear hierarchy that allows a "Scan" level (Search Results) and a "Deep Dive" level (Investment Analysis).

## 5. Tone of Voice
- **Direct & Empirical:** Use terms like "Projected Yield," "Market Gap," and "Transacted Price" rather than marketing-speak.
- **No Fluff:** Minimize decorative icons or "empty" illustrations. If an element isn't data, it should be a navigation control.

# Component Library: Lelong Analytical Ledger

This document defines the core UI components for the Lelong Analytical platform. Our components are designed for high information density, prioritizing data throughput and professional utility.

---

## 1. Global Navigation

### TopAppBar (Analytical Header)
*   **Purpose:** Provides context and primary actions without occupying excessive vertical space.
*   **Visuals:**
    *   Background: `#F7F9FB` (Cool Gray) or semi-transparent backdrop blur.
    *   Logo: Deep Navy (`#1B365D`), bold, tight tracking.
    *   Actions: Minimalist icons for search, wallet, or user profile.
*   **Density:** 64px height on mobile.

### BottomNavBar (Global Utility)
*   **Purpose:** One-handed navigation between core analytical views.
*   **Destinations:** Insights, Watchlist, Search, Profile.
*   **Visuals:**
    *   Background: White/90% with heavy backdrop blur.
    *   Active State: Deep Navy icon with a subtle background pill or text label.
    *   Inactive State: Muted Slate icons.
*   **Typography:** 10px-11px uppercase, bold.

---

## 2. Data Visualization Components

### Metric Highlight Cards
*   **Purpose:** Display top-level KPIs (e.g., Active Listings, Market Gap).
*   **Structure:** Label (top), Large Value (center), Trend/Detail (bottom).
*   **Visuals:** Borderless, white surface, subtle drop shadows (level 1).

### Sparklines & Micro-Charts
*   **Purpose:** Show trends within list items or dashboards without a full chart view.
*   **Visuals:** Monochromatic blue or semantic colors (Green for success, Red for alert).

### Area Heatmaps (Progress Bars)
*   **Purpose:** Visualize market saturation or area demand.
*   **Logic:** Multi-segment bars with percentage labels.

---

## 3. The Analytical Listing Card

### High-Density Property Card
*   **Purpose:** The "workhorse" component. Displays maximum data for rapid scanning.
*   **Required Fields:**
    1.  **Thumbnail:** High-quality image with "Hot" or "New" status tags.
    2.  **Headline:** Project/Location name in semi-bold Manrope.
    3.  **The "Big Three" Metrics:** Price, Yield (%), and Market Gap (%).
    4.  **Meta:** Auction date and tenure.
*   **Interaction:** Tapping leads to the Investment Deep Dive.

---

## 4. Layout & Containers

### Data Grid / Table
*   **Purpose:** For "Search Results" or "Recent Comparables."
*   **Logic:** zebra-striping (alternating backgrounds) for row readability.
*   **Typography:** Monospaced-style numeric fonts where possible for alignment.

### Status Badges
*   **Variants:**
    *   **Hot Deal:** Blue background, white text.
    *   **Foreclosure:** Soft red tint.
    *   **New Listing:** Soft blue tint.
*   **Shape:** `ROUND_FOUR` (minimal rounding).

---

## 5. Forms & Filters

### Analytical Filter Bar
*   **Purpose:** Refine large datasets.
*   **Controls:** Multi-select chips, dropdowns for "Yield Range," and location search.
*   **Density:** Tight padding (8px) to keep filters visible alongside results.

---

## 6. Typography Scale
*   **H1 (Headers):** 24px-28px, Bold, -0.02em tracking.
*   **Body (Data):** 14px-16px, Semi-Bold, High contrast.
*   **Labels (Secondary):** 12px, Medium, Muted Slate.
*   **Captions:** 10px, Regular, Uppercase.
