# PRODUCT.md — MoonTech Casting (Studio frontend)

## Register
product

## What it is
A localhost studio tool for creating and browsing reusable synthetic actors
("talent") used to produce AI-generated ads. Two jobs: browse the roster of
saved models, and cast a new one (describe a look → generate a base sheet →
pick one frame per angle → save a card + reference sheet).

## Users & purpose
A single operator (the person building the ads) on their own machine. They are
in a focused production task, not browsing for pleasure. The interface must get
out of the way: judge realism while picking frames, move quickly from brief to
saved model. Density and clarity beat spectacle.

## Brand personality
Deep-space, precise, cinematic-but-restrained. "MoonTech" — a quiet, high-end
production tool, not a consumer toy. Confidence and control, not delight.

## Anti-references
- Consumer AI-avatar apps (playful, rounded, sticker-like).
- SaaS-marketing dashboards (hero metrics, gradient text, eyebrow kickers).
- Decorative numbered-section scaffolding used where there is no real sequence.

## Accessibility
Body/label text ≥ 4.5:1 on the dark surface. Full `prefers-reduced-motion`
support. Keyboard-focusable controls with a visible focus ring (violet).

## Strategic design principles
- The tool disappears into the task; consistency over surprise.
- One numbered sequence is allowed where the flow IS ordered (the create
  console: Brief → Base sheet → Save). Numbers are NOT used as decoration on
  non-sequential panels (e.g. the detail page's Reference/Identity panes).
- Committed dark palette (indigo/violet on near-black); accent reserved for
  primary action, current selection, and state — not decoration.
- Real generated imagery is the hero; chrome stays quiet around it.
