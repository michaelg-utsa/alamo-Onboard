# AlamoOnboard — User Stories

**Format:** Each story has a stable ID (US-NN), Given/When/Then acceptance criteria, and numbered manual walkthrough steps the TA can follow against the running system without reading source code.

**Running the system:** `docker compose up` → open http://localhost:7860

**Note:** Screenshots for each story are in `docs/assets/stories/us_NN_expected.png`.

---

## US-01 — Ask a factual question about CPS Energy

**As a** new San Antonio resident,  
**I want to** ask the assistant about CPS Energy deposit requirements,  
**So that** I can understand what upfront costs to expect before I start service.

### Acceptance Criteria

- **Given** the chat interface is loaded and idle,
- **When** the user asks "What is the deposit for CPS Energy?",
- **Then** the assistant responds with a factual answer citing a specific source title and provider (e.g., "(CPS Energy, New Service Deposit)"), without asking the user to fill out a form.

### Manual Walkthrough

1. Open http://localhost:7860 and wait for the welcome message to appear (loading completes in ≤120 seconds). Click **Reset**, then click **Confirm Reset** once prompted to ensure it is a fresh session. Observe that the Available Commands panel on the right shows the idle buttons (Start CPS Energy signup, Start SAWS signup, etc.).
2. In the chat input, type: `What is the deposit for CPS Energy?` and click **Send**.
3. While the assistant is processing, observe that the message you just sent is visible in the chat history above the input box. The assistant's response area may or may not show a loading indicator, but your submitted message should already be displayed.
4. Observe the assistant's reply. Verify that:
   - The reply mentions a deposit amount or policy.
   - The reply includes an inline citation in the format `(CPS Energy, <title>)`.
   - The assistant does **not** ask the user to start a signup form.
5. The Available Commands panel on the right still shows the idle buttons (Start CPS Energy signup, Start SAWS signup, etc.).

**Expected end state:** A factual answer with citation is displayed. The checklist sidebar remains unchanged.

**Reference screenshot:** `docs/assets/stories/us_01_expected.png`

---

## US-02 — View the move-in checklist

**As a** new resident,  
**I want to** see the current status of all my utility setup tasks,  
**So that** I know what is still pending and what I have completed.

### Acceptance Criteria

- **Given** the assistant is running and the user has not completed any signups,
- **When** the user clicks the "Show my checklist" button or types `show my checklist`,
- **Then** the assistant displays a formatted checklist showing all three services (CPS Energy, SAWS, Trash/Recycling) each with status "pending".

### Manual Walkthrough

1. Click **Reset**, then click **Confirm Reset** once prompted to start a fresh session. Observe that both the checklist and chat history are cleared, with no error messages visible.
2. Click the **Show my checklist** button in the Available Commands panel.
   - Observe that the command `show my checklist` is pasted into the chat input.
3. Click **Send**.
4. Observe the assistant's reply. Verify that:
   - All three services are listed: CPS Energy electric & gas; SAWS water & sewer; and Trash, recycling & organics.
   - Each shows status `pending` with the `[ ]` symbol.
5. The checklist sidebar on the right shows the same status for all three items.

**Expected end state:** Checklist displayed in chat. All three items are `[ ] (pending)`.

**Reference screenshot:** `docs/assets/stories/us_02_expected.png`

---

## US-03 — Start and complete the CPS Energy signup form

**As a** new resident,  
**I want to** fill out the CPS Energy new service form,  
**So that** I have a record of my service start request ready to submit.

### Acceptance Criteria

- **Given** the assistant is idle,
- **When** the user says "start cps_energy" and confirms with "yes",
- **Then** the assistant guides the user through all 14 fields one at a time, accepts valid input, and presents a review summary at the end.
- **And When** the user types "submit",
- **Then** the CPS Energy item on the checklist is marked as completed.

### Manual Walkthrough

1. Click **Reset**, then click **Confirm Reset** once prompted to start a fresh session. 
2. Click **Start CPS Energy signup** in the Available Commands panel and click **Send**.
3. The assistant asks for confirmation. Click **Yes** and click **Send**.
4. The form begins. Fill in the following values when prompted (press Enter after each unless otherwise specified):
   - First name: `Alex`
   - Last name: `Kim`
   - Date of birth: `1990-05-15`
   - SSN or driver license: `123-45-6789` (9-digit SSN — note it is masked in the summary)
   - Email: `alex.kim@example.com`
   - Phone: `2105551234`
   - Service address: `123 Main St`
   - City: Type `keep` and press Enter to accept pre-filled `San Antonio`.
   - State: Click `Keep pre-filled value`. Observe that the command `keep` is pasted into the chat input. Click **Send** to accept pre-filled `TX`.
   - ZIP: `78205`
   - Requested start date: enter a date at least 2 business days from today in YYYY-MM-DD format (e.g., `2027-05-07`, adjusted as needed)
   - Military relocation: `no`. Observe that it accepts `no` as well as `false`
   - Paperless billing: `skip`. Observe that it allows you to skip optional components of the form.
   - Budget billing: `keep`
5. After the last field, observe the **Review** summary showing all entered values. Verify SSN is masked (shows `***-**-6789`).
6. Click **Submit form** in the Available Commands panel and click **Send**.
7. Observe the assistant reports submission, with the note that the program is a prototype and does not literally submit the form. Also observe that the CPS Energy item in the checklist sidebar changes to `[x] (completed)`.

**Expected end state:** CPS Energy marked completed in sidebar and in chat. The Review summary was shown before submission.

**Reference screenshot:** `docs/assets/stories/us_03_expected.png`

---

## US-04 — Start and complete the SAWS signup form after CPS Energy form

**As a** new resident,  
**I want to** fill out the SAWS water service form,  
**So that** water is turned on before I move in.

### Acceptance Criteria

- **Given** the CPS Energy signup has been completed (profile contains name, email, phone, address),
- **When** the user starts the SAWS signup,
- **Then** the form pre-fills name, email, phone, address, city, state, and ZIP from the profile, allowing the user to accept them with "keep".
- **And When** the user submits,
- **Then** the SAWS item is marked completed.

### Manual Walkthrough

1. Complete US-03 first so the profile contains name, email, phone, and address.
2. Click **Start SAWS signup** and click **Send**.
3. Confirm with **Yes**.
4. For each field that shows a pre-filled hint, click **Keep pre-filled value** and click **Send**.
   - Fields that pre-fill: first_name, last_name, Date of birth, email, phone, service_address, service_city, service_state, service_zip.
5. For the remaining fields requiring new input:
   - Last 4 of SSN: `6789`
   - Requested start date: a date at least 5 business days from today in YYYY-MM-DD format (e.g., `2027-05-07`, adjusted as needed)
   - Proof of residency type: type `1` or `Lease agreement`
   - Letter of credit available: `no`
   - DV survivor waiver: `no`
6. Review the summary. Click **Submit form** and click **Send**.
7. Verify the SAWS item in the sidebar changes to `[x] (completed)`.

**Expected end state:** SAWS marked completed. Pre-filled fields shown with "(we have '...' on file)" hints.

**Reference screenshot:** `docs/assets/stories/us_04_expected.png`

---

## US-05 — Use "keep all" to accept all pre-filled form values

**As a** returning user who has already filled out one form,  
**I want to** start a second form and accept all pre-filled values at once,  
**So that** I don't have to press "keep" individually for every pre-filled field.

### Acceptance Criteria

- **Given** the profile already has name, email, phone, and address from a previous form,
- **When** the user starts the COSA Solid Waste form and types "keep all",
- **Then** the assistant skips all consecutive pre-filled fields in one step and lands on the first field that requires new input.

### Manual Walkthrough

1. Complete US-03 so the profile has name, phone, and address.
2. Click **Start City of SA trash signup** and click **Send**. Confirm with **Yes**.
3. When the first field prompt appears (First name, which is pre-filled), type `keep all` and press Enter.
4. Observe the assistant skips first_name, last_name, phone, service_address, service_zip (all pre-filled) and lands on the first gap field (likely `cps_account_number` or `carts_present`).
5. Fill in the remaining fields:
   - CPS account number: optional field, so type `skip` and press Enter
   - Carts present: `1` (or `Yes, all three`)
   - Preferred brown cart size: `2` (or `Medium`)
   - Look up collection day: `no` (collection day lookup is a planned future feature; type `no` or `skip` to continue)
   - Text alerts: `no`
6. Review summary and click **Submit form**.

**Expected end state:** Multiple pre-filled fields were accepted in one "keep all" command. Form completed successfully.

**Reference screenshot:** `docs/assets/stories/us_05_expected.png`

---

## US-06 — Pause a form and resume it later

**As a** user mid-form who needs to ask a question,  
**I want to** pause the form without losing my progress,  
**So that** I can ask a question and then pick up where I left off.

### Acceptance Criteria

- **Given** the CPS Energy signup is in progress on the email field,
- **When** the user types "pause",
- **Then** the assistant confirms the pause, exits guided mode, and the user can ask a free-form question.
- **And When** the user types "resume cps_energy",
- **Then** the assistant resumes at exactly the field where the form was paused.

### Manual Walkthrough

1. Click **Reset**, then click **Confirm Reset** once prompted to start a fresh session. Observe that both the checklist and chat history are cleared, with no error messages visible.
2. Click **Start CPS Energy signup** and click **Send**.
3. The assistant asks for confirmation. Type `I have a question` and press Enter. Observe that the assistant returns to idle chat (the Available Commands panel shows the idle buttons) and does not loop back to the confirmation prompt.
4. Click **Start CPS Energy signup** again and click **Send**.
5. The assistant asks for confirmation. Type `YeS!?!` and press Enter. Observe that it accepts inputs where `yes` appears with any capitalization or trailing punctuation.
6. Fill in first name (`Alex`) and last name (`Kim`).
7. When prompted for date of birth, type `pause` and press Enter (or click **Pause form to ask a question**).
8. Observe the assistant says the form is paused and describes how to resume. The Available Commands panel updates to show **Resume cps_energy** and **Cancel & discard form** — these replace the in-form buttons and allow either resuming or fully discarding the paused form.
9. Type: `What is the deposit for CPS Energy?` and press Enter. Verify the assistant answers normally (not as a form field).
10. Click **Resume cps_energy** in the Available Commands panel and click **Send** (or type `resume cps_energy` and press Enter).
11. Verify the assistant resumes at the **date of birth** field (the one that was interrupted).

**Expected end state:** Form resumes at the exact field where it was paused. No data was lost.

**Reference screenshot:** `docs/assets/stories/us_06_expected.png`

---

## US-07 — Enter an invalid email and see a validation error _(error path)_

**As a** user filling out the CPS Energy form,  
**I want to** be told immediately when I enter an invalid email,  
**So that** I can correct it before submitting.

### Acceptance Criteria

- **Given** the CPS Energy signup is active and the email field is the current field,
- **When** the user enters `notanemail`,
- **Then** the assistant rejects the input with a clear error message ("That doesn't look like a valid email address.") and re-prompts the same field without advancing.
- **And When** the user then enters `alex@example.com`,
- **Then** the assistant accepts it and advances to the next field.

### Manual Walkthrough

1. Click **Reset**, then click **Confirm Reset** once prompted to start a fresh session. Observe that both the checklist and chat history are cleared, with no error messages visible.
2. Click **Start CPS Energy signup** and click **Send**.
3. Fill in first name (`Alex`), last name (`Kim`), date of birth (`1990-05-15`), SSN (`123-45-6789`). For each question, press Enter after providing the answer to move on to the next field.
4. When prompted for **Email**, type `notanemail` and press Enter.
5. Observe the assistant replies with the error: **"That doesn't look like a valid email address."** and re-prompts the email field (does not advance to phone).
6. Type `alex@example.com` and press Enter.
7. Observe the assistant accepts the email and prompts for the next field **Phone**.

**Expected end state:** The email field was not advanced until a valid email was entered. Error message was displayed.

**Reference screenshot:** `docs/assets/stories/us_07_expected.png`

---

## US-08 — Request a start date too soon and see a lead time error _(error path)_

**As a** user filling out the SAWS form,  
**I want to** be informed when my requested start date is too soon,  
**So that** I can pick a valid date that SAWS will honor.

### Acceptance Criteria

- **Given** the SAWS signup is active and the requested start date field is current,
- **When** the user enters tomorrow's date (1 business day from today),
- **Then** the assistant rejects it with an error stating the earliest allowed date (at least 5 business days from today) and re-prompts the same field.
- **And When** the user enters a valid date (≥ 5 business days from today, not a weekend),
- **Then** the assistant accepts it and advances.

### Manual Walkthrough

1. Click **Reset**, then click **Confirm Reset** once prompted to start a fresh session. Observe that both the checklist and chat history are cleared, with no error messages visible.
2. Click **Start SAWS signup** and click **Send**.
3. Fill in first name (`Alex`), last name (`Kim`), date of birth (`1990-05-15`), last 4 SSN (`6789`), email (`alex@example.com`), phone (`2105551234`), address (`123 Main St`), city (`keep`), state (`keep`), ZIP (`78205`). For each question, press Enter after providing the answer to move on to the next field.
4. When prompted for **Requested start date**, type today's date or another date prior to 5 business days from today in YYYY-MM-DD format (e.g., `2026-05-14`).
5. Observe the error message: something like **"Pick a date on or after 2026-05-12 (at least 5 business days out)."**, with the specific date depending on the date the program is being run. The field is re-prompted; the workflow does not advance.
6. Enter the earliest valid date shown in the error (e.g., `2026-05-19`).
7. Observe the assistant accepts the date and prompts for **Proof of residency type**.

**Expected end state:** Date too soon was rejected with the exact earliest valid date in the error. A valid date was accepted.

**Reference screenshot:** `docs/assets/stories/us_08_expected.png`

---

## Story Summary

| ID | Title | Type | Key feature tested |
|---|---|---|---|
| US-01 | Ask about CPS Energy deposit | Happy path | RAG retrieval + inline citations |
| US-02 | View move-in checklist | Happy path | Checklist rendering, Reset |
| US-03 | Complete CPS Energy signup | Happy path | Full 14-field form FSM, submit |
| US-04 | Complete SAWS signup | Happy path | Cross-form pre-fill from profile |
| US-05 | Use keep-all command | Happy path | Bulk pre-fill acceptance |
| US-06 | Pause and resume a form | Happy path | Workflow persistence across turns |
| US-07 | Invalid email validation | **Error path** | Field validator rejection + retry |
| US-08 | Start date lead time error | **Error path** | Business-day lead time validator |
