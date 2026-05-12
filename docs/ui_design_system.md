# UI Design System

## Principles

- Use a quiet, modern, low-distraction interface with clear hierarchy, generous whitespace, and high readability.
- Prefer white, gray, black, and low-saturation accents.
- Do not copy OpenAI trademarks, logos, proprietary illustrations, brand copy, or protected visual assets.
- Keep operational pages workflow-first instead of decorative or marketing-heavy.

## Tokens

- Background: neutral page background and muted surface bands.
- Surface: white or near-white panels with thin borders.
- Text: high-contrast primary text and subdued secondary text.
- Accent: one restrained action color with success, warning, and danger states.
- Radius: moderate rounded corners for panels and compact controls.
- Shadow: subtle elevation only where separation is needed.

## Layout

- Use a left rail for primary app navigation.
- Use a central work area for the active workflow.
- Use a right inspector where contextual evidence, safety, artifacts, or metadata are useful.
- Prefer constrained content width for reading surfaces and denser grids for operational summaries.
- Mobile layouts should stack navigation, primary content, and inspector content without overlap.

## Components

- Cards: individual repeated items, status summaries, or contained tools; avoid cards inside cards.
- Buttons: clear commands with icon+text when helpful; destructive states must be visually distinct.
- Badges: compact status labels for ready, warning, blocked, disabled, and pending states.
- Tables: sparse, readable, sortable-ready presentation with stable column sizing.
- Inspector: contextual details, traces, manifests, artifact links, and safety state.
- Command Bar: primary page actions and mode switches.
- Stepper: workflow stage display for Dataset, Preparation, Model, Results, History, Agent, and Optimization.

## Legacy Compatibility

- Legacy Data Lab pages may receive light CSS convergence, but IDs, forms, and verification markers must remain stable.
- Public pages can be visually simplified without changing auth, public briefing, or workspace entry dependencies.
