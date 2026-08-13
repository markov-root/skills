---
knowledge:
  version: 1
  id: accessibility
  summary: Design and verify user-facing systems for disability access across semantics, interaction, content, and assistive technologies.
  routes: [user-facing-interaction]
  sources: [src-accessibility-standards]
---

# Accessibility Engineering

> **Purpose:** Treat accessibility as a product quality attribute and compatibility requirement,
> not a final automated scan.
>
> **Read this when:** designing or changing web, mobile, desktop, terminal, document, media, or
> assistive-technology-facing behavior.

---

## Contract and Standard

**Standard/fact (verified 2026-07-30):** WCAG 2.2 is a W3C Recommendation. W3C advises using WCAG
2.2 for current web accessibility work, while noting that it does not address every user need. Use
the applicable conformance target and current legal requirements for the product's jurisdictions.
Source: [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/). Re-verify before setting or publishing a
conformance target.

**Legal note:** Accessibility law and required standards vary by jurisdiction, sector, procurement
contract, and product type. Engineering evidence supports—but does not itself establish—legal
compliance.

Define:

- users and access needs in scope;
- platforms, browsers, devices, input modes, zoom/reflow, and assistive technologies supported;
- target standard/version/level and any product-specific requirements;
- manual and automated evidence required for release;
- owner and remediation timeline for known exceptions.

## Build Semantics First

**Project default for the web:** Use native semantic HTML and platform controls before custom
widgets. Correct names, roles, values, relationships, and states give browsers and assistive
technologies interoperable information.

- preserve a logical heading and landmark structure;
- associate labels, instructions, errors, and help with controls;
- give images and media appropriate text alternatives, captions, transcripts, or intentional empty
  alternatives;
- announce meaningful dynamic changes without flooding users;
- expose table headers and relationships;
- keep DOM/read order consistent with visual and keyboard order.

ARIA can repair missing semantics when no native element fits. Incorrect ARIA can make a usable
control inaccessible; test the resulting accessibility tree and interaction.

## Keyboard, Focus, and Input

- Every interactive function should be operable without a pointer when the platform supports it.
- Focus order follows the task; focus is visible and not obscured.
- Opening, closing, validation, routing, and asynchronous updates move or retain focus intentionally.
- Avoid keyboard traps; provide a documented escape from composite widgets.
- Pointer targets, gestures, timing, and drag interactions have accessible alternatives.
- Do not assume touch, mouse, keyboard, voice, switch, or screen reader is the only input mode.

## Perception and Motion

- Do not communicate meaning by color, position, sound, or motion alone.
- Meet applicable text and non-text contrast requirements; test states, placeholders, charts, and
  focus indicators, not only body text.
- Support zoom, reflow, text spacing, orientation, and user font settings within the declared
  platform contract.
- Respect reduced-motion and other platform preferences; avoid flashing and unnecessary vestibular
  triggers.
- Error messages identify the problem and recovery path in text.

## Mobile, Desktop, Terminal, and Documents

Platform-native accessibility APIs, focus systems, text scaling, high-contrast modes, reduced
motion, screen readers, and input conventions are part of compatibility. For terminals, preserve
plain-text meaning, controllable color, non-interactive modes, and screen-reader-friendly output.
For PDFs/documents, use tagged structure, reading order, language metadata, meaningful links, and
accessible source formats.

## Testing Strategy

Automated tools catch useful classes such as missing names, invalid roles, and some contrast errors.
They do not establish usability or conformance.

Use layered evidence:

1. lint/static rules and component-level accessibility tests;
2. automated browser/platform scans on representative states;
3. keyboard-only and zoom/reflow review;
4. accessibility-tree inspection;
5. screen-reader testing on the declared platform matrix;
6. high-contrast, reduced-motion, touch/target, error, loading, and timeout scenarios;
7. usability research with disabled people for important workflows.

Regression-test shared components and critical journeys, but retain manual exploration: assistive
technology interaction depends on context and composition.

## Inclusive Design and Content

Accessibility is broader than technical conformance. Use clear language, predictable navigation,
recoverable actions, tolerant input, alternatives to memory-heavy tasks, and human support for
high-impact failures. Include disabled users early enough that findings can change the design.

Publish an accessibility statement when appropriate: supported standard, known limitations,
contact/reporting route, and response process. Do not claim “fully accessible” from a scanner score.

## Release and Operations

- make accessibility acceptance criteria part of design and code review;
- assign findings an owner, severity, affected users, workaround, and target;
- test third-party widgets and content, not only code owned locally;
- monitor regressions after design-system, framework, browser, and platform upgrades;
- preserve accessibility in incident fallbacks, consent flows, authentication, support, and status
  communication.

## Meta-Question

Can people with different sensory, motor, cognitive, speech, and situational needs perceive,
understand, navigate, operate, and recover from the product using their chosen platform tools?
