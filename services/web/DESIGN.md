# Research interface

Audience: a live fellowship demonstration and subsequent evidence review.
Register: product UI. Preserve the lab's dark teal palette.

## Typography

IBM Plex Sans: interface, headings and prose. IBM Plex Mono: readings, axes and code.
Unmodified WOFF2 fonts are stored in public/fonts with the upstream OFL and source revision.
No font service is contacted at runtime. Regular faces are preloaded by research.html.

Semantic rem ramp: meta .75; label .875; body 1; heading 1.25; title 1.75;
readout 2; display 2.5. Prose uses body size and 1.55 leading, capped at 65–75ch.
Dense axis labels, metadata and heatmap cells use smaller caption roles; they are not prose.
Use 400 for display headings, 500 for section labels, 600 for emphasis and buttons.
Tabular numbers for measurements. Maximum three loaded sans weights, two mono weights.

## Copy

Use subjects and results: System, Disturbance, Control, Internals, Findings.
Avoid rhetorical headings, marketing claims and instructions explaining obvious controls.
Keep recorded/live status, model identity, units and conditional A/B labels visible.
Put narrative in speaker notes and methodology in disclosures; retain source evidence.

## References

https://www.ibm.com/design/language/typography/typeface/
https://www.ibm.com/design/language/typography/type-scale/
https://vercel.com/geist/typography
Impeccable product, typeset and distill guidance.

## Interaction refinement · September 2026

Reference: https://www.lfgcontentco.com/ — strong display hierarchy, generous working space, rolling navigation labels and responsive hover states. Adapted for evidence review: no intro loader or cursor replacement. Barlow Condensed SemiBold is reserved for chapter headings (3.5rem desktop, 2.75rem mobile); IBM Plex continues to carry controls and readings. Fonts remain local with upstream licenses.

Chapter navigation uses a vertical rail on desktop and a horizontal strip on mobile. Control nodes preview their recorded evidence on mouse hover and select on click or keyboard focus; touching selects directly. The replay crosshair reads saved, quality-checked samples only up to the playback cursor. The range input supplies keyboard and touch scrubbing. Navigation label rolls and focus highlights use 160–220ms transitions; reduced-motion removes transforms and animation.
