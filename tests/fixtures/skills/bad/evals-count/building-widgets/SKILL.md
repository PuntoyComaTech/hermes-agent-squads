---
name: building-widgets
description: "Builds dashboard widgets from a data contract. Use when a card asks for a new widget or a widget fix."
---

# Building widgets

## When to Use

- A kanban card asks for a new dashboard widget.
- A widget renders wrong data or breaks the layout.

## Procedure

1. Read the data contract in `references/widget-contract.md`.
2. Copy `templates/widget.html` into the site repo.
3. Run `scripts/render_widget.py --input data.json` to preview it.
4. Run `scripts/check_widget.sh widget.html` before handing off.

## Pitfalls

- Never invent fields the contract does not define.
- Keep every color in the design tokens file.

## Verification

- `scripts/check_widget.sh` exits 0.
- The preview matches the card's acceptance criteria.
