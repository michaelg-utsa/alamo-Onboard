# Usage Guide

This guide walks through each user story in `docs/STORIES.md`. Every section corresponds to one story and describes how to use that feature from the running application.

**Start the app:** `docker compose up` → open http://localhost:7860

---

## US-01 — Asking factual questions

The assistant can answer questions about CPS Energy, SAWS, and City of San Antonio services using its knowledge base. It always cites the source of its answer.

**Try these prompts:**
- `What is the deposit for CPS Energy?`
- `How much is the SAWS residential deposit?`
- `What are the trash cart sizes and costs?`
- `Does CPS Energy have a military discount?`
- `How many business days notice does SAWS need?`

**What to expect:** The assistant retrieves relevant passages and responds with a factual answer that includes an inline citation like `(CPS Energy, New Service Deposit)`. It will not ask you to fill out a form unless you explicitly ask to sign up.

---

## US-02 — Viewing the checklist

The move-in checklist shows the status of all three services (CPS Energy, SAWS, Trash/Recycling).

**How to access:**
- Click **Show my checklist** in the Available Commands panel (right side), then press Enter.
- Or type `show my checklist` directly.

**Status symbols:**
- `[ ]` Pending — not yet started
- `[~]` In progress — form started but not submitted
- `[x]` Completed — form submitted
- `[-]` Skipped — marked as not needed

The checklist is also shown in the sidebar and updates automatically as you complete forms.

**Resetting:** Click **Reset** to clear all progress and start fresh (for demos or testing).

---

## US-03 — CPS Energy signup

The CPS Energy signup walks you through 14 fields to prepare a new service request.

**To start:**
1. Click **Start CPS Energy signup** → press Enter → click **Yes** → press Enter.

**Form fields:**
- Name, date of birth, SSN or driver license, email, phone, service address, requested start date (≥ 2 business days from today), and optional preferences (military status, paperless billing, budget billing).

**During the form:**
- Click **Keep pre-filled value** when a field shows a value already on file.
- Click **Keep all remaining pre-filled values** to accept all consecutive pre-filled fields at once.
- Click **Undo last answer** to go back one field.
- Click **Pause form to ask a question** to step away without losing progress.
- Click **Cancel & discard current form** to abandon the form entirely.

**At the review screen:**
- Click **Submit form** to mark CPS Energy as completed on your checklist.
- Click an **Edit:** button to jump back to a specific field.

---

## US-04 — SAWS signup

The SAWS signup has 14 fields including proof of residency type.

**To start:** Click **Start SAWS signup** → confirm with **Yes**.

**Pre-fill:** If you completed CPS Energy first, your name, email, phone, and address are already on file. You'll see `(we have '...' on file - reply 'keep' to use it)` for each pre-filled field.

**Key difference from CPS Energy:**
- Requires **Last 4 digits of SSN** (not full SSN or driver license)
- Requires **Proof of residency type** — choose from: Lease agreement, Closing documents, or Utility bill in your name
- Lead time: **5 business days** minimum (vs 2 for CPS Energy)

---

## US-05 — Keep All command

If you've already completed one form, subsequent forms pre-fill your name, phone, and address. Instead of pressing **Keep** for each field individually, use **Keep all remaining pre-filled values** to skip all consecutive pre-filled fields in one step.

**When to use:** After starting a form, on the first pre-filled field, click **Keep all remaining pre-filled values**.

The assistant will advance through all consecutive pre-filled fields and stop at the first field that needs new input.

---

## US-06 — Pausing and resuming

If you need to ask a question mid-form without losing your progress, use **Pause**.

**To pause:** Click **Pause form to ask a question** during any form field.

The assistant will save your progress and exit guided mode. You can then ask any question (e.g., "What is the SAWS deposit?"). The Available Commands panel shows the idle buttons.

**To resume:** Click **Resume cps_energy** (or the relevant service) in the Available Commands panel, then press Enter. The form picks up exactly where it left off.

---

## US-07 — Email validation error _(error path)_

If you enter an invalid email address during a form, the assistant rejects it immediately and re-prompts the same field.

**Expected error message:** `That doesn't look like a valid email address.`

The form does not advance until a valid email (format `user@domain.tld`) is entered.

**Other validation errors you may encounter:**
- Phone: must be a 10-digit US number
- ZIP: must be 5-digit or ZIP+4
- Address: must start with a house number followed by a street name

---

## US-08 — Start date lead time error _(error path)_

CPS Energy requires at least **2 business days** notice; SAWS requires **5 business days**. Weekends are not valid start dates.

If you enter a date that is too soon, the assistant rejects it and tells you the earliest valid date:

**Example error:** `Pick a date on or after 2026-05-12 (at least 5 business days out).`

Enter the earliest valid date shown or any later weekday date.
