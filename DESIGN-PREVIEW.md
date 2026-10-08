# Cinematic product UI experiment — local only

Website branch: `experiment/cinematic-product-demo` (based on dcd1666).
Both product branches: `experiment/product-ui-motion`.

## Run

With the three T7 repositories installed, run `node scripts/preview-design.mjs`
from `/Volumes/T7/buildbyray`. Ports 3210, 3211, and 3212 must be available.
Do not deploy this experiment yet.

- Website: http://127.0.0.1:3210/projects/text2bi and /projects/ai-interview
- Text2BI UI: http://127.0.0.1:3211/?design=1
- Interview UI: http://127.0.0.1:3212/?design=1

The website embeds the corresponding local product UI, not a screenshot. The
right-side stage palette, text, navigation and existing scroll-snap logic are
unchanged. Device opening is a 2.5D photographic hinge animation, not a full 3D
MacBook model. Close-up stages crop the external hardware, not the product input.
Replay opening restarts it. Reduced motion shows the open device immediately.

## Two layers of change

Each product has an additive `product-polish.css` for the existing application
and a development-only `DesignPreview` entry for the proposed focused workflow.
The focused preview is an interactive UI concept: it uses isolated example data,
never connects to backend APIs, never uploads files, and never starts a camera or
microphone. Its generated report, transcript and feedback are explicit examples,
not live model outputs. It is not yet wired into the full production workflow.
Normal application auth, APIs, and business logic are unchanged. No tokens are set.
The website preserves previous screenshots as the non-development fallback.

Refine animates a sample layout change without changing source totals; Refresh
changes the sample totals and allows comparison with the previous dataset.
Full previews support sample import, editable requests, simulated generation,
data question, refinement, refresh, interview preparation, conversation and review.

## Asset source / publication review

MacBook frame supplied by the user's requested Apple reference:
https://www.apple.com/v/macbook-pro/ax/images/overview/performance/performance_mbp_hw__dsz2n8vqr16q_large.jpg
Source page: https://www.apple.com/macbook-pro/
Used for this local study only. No license or Apple endorsement is claimed.
Review asset usage rights, or replace with a licensed device asset, before publication.

No GitHub push and no production deployment were performed. Pre-existing local
changes and raw personal files in all three repositories remain untouched.
