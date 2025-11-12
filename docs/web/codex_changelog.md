# Web Codex Change Log

Document noteworthy web-facing changes implemented via Codex tasks. Keep the newest entries at the top.

## 2025-11-12 — Fix OVATION south grid isolines

- Corrected the south hemisphere OVATION grid traversal so probability contours and Kp isolines scan latitude rows from 0° down to −90°.
- Ensured viewline and Kp isolines share the same latitude orientation, restoring contours near −60° to −75° instead of near the equator.
