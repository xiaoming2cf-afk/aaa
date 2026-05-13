# UI Design System

## Principles

- Use a quiet, modern, low-distraction interface with clear hierarchy, generous whitespace, and high readability.
- Prefer white, gray, black, and restrained neutral surfaces. Green is reserved for success states, not primary branding.
- Do not copy OpenAI trademarks, logos, proprietary illustrations, brand copy, or protected visual assets.
- Keep operational pages workflow-first instead of decorative or marketing-heavy.
- The current SPA visual pass intentionally moves away from the previous green/teal admin-console palette toward a neutral AI workspace palette while using only project-owned UI styles and copy.

## Tokens

- Background: `--bg: #f7f7f5` with no page-level gradients.
- Surface: `--surface: #ffffff`, `--surface-muted: #f1f1ef`, and `--surface-elevated: #ffffff`.
- Text: `--text: #111111` with `--muted: #6f6f6a` for secondary information.
- Borders: `--border: #e4e4df` and `--border-strong: #d4d4ce`.
- Accent: `--accent: #111111` for primary actions; `--accent-soft: #eeeeea` for selected and hover states.
- Status: `--danger: #b42318`, `--warning: #9a6700`, and `--success: #1f7a55`.
- Radius: `--radius-sm`, `--radius-md`, and `--radius-lg` keep controls compact and cards softly rounded.
- Shadow: `--shadow-soft` is subtle and optional; borders should carry most separation.

## Layout

- Use a left rail for primary app navigation.
- Use a central work area for the active workflow.
- Use a right inspector where contextual evidence, safety, artifacts, or metadata are useful.
- Prefer constrained content width for reading surfaces and denser grids for operational summaries.
- Mobile layouts should stack navigation, primary content, and inspector content without overlap.

## Components

- Sidebar: use a light surface, a right border, neutral text, and soft gray active states. Overview remains first, Research and Data Lab remain adjacent, Data Lab Agent remains distinct from the Data Lab hub, and legacy links stay grouped.
- Cards: use white surfaces, 1px neutral borders, 12px radius, consistent padding, and little or no shadow. Avoid large gradients and nested-card compositions.
- Buttons: primary actions use black with white text; secondary actions use white with a border; ghost actions use transparent backgrounds with gray hover; danger actions use red.
- Badges: compact neutral labels by default. Use green only for success, amber only for warning, and red only for danger.
- Tables: sparse, readable, sortable-ready presentation with stable column sizing.
- Inspector and risk panels: use neutral cards with clear headings; warning cards should be amber-tinted but restrained.
- Command Bar: keep page actions compact and low-emphasis; avoid treating refresh or secondary actions as primary CTAs.
- Stepper: workflow stage display for Dataset, Preparation, Model, Results, History, Agent, and Optimization.
- Surface primitives: use shared `surface`, `metric-card`, `action-card`, `inspector-panel`, and `command-bar` classes before creating page-specific card styles.

## Legacy Compatibility

- Legacy Data Lab pages may receive light CSS convergence, but IDs, forms, and verification markers must remain stable.
- Public pages can be visually simplified without changing auth, public briefing, or workspace entry dependencies.
- Legacy flow strips and panels should make preview, preflight, manifest, and best-effort lineage visible without changing endpoint contracts.
