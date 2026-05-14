# Model Card — AlamoOnboard

---

## Intended Use

AlamoOnboard is a conversational assistant designed to help people relocating to San Antonio, Texas set up utility and city services (CPS Energy, SAWS, City of San Antonio Solid Waste). Its intended users are:

- **New residents** who need to activate utilities before moving in
- **Housing navigators and relocation specialists** who help clients set up services
- **Students and researchers** studying agentic AI applied to civic services (CS 6263 course context)

The system is intended for use through its Gradio web chat interface. It answers factual questions by retrieving information from official provider websites, guides users through service signup forms field-by-field, and tracks progress on a move-in checklist. All form data is collected locally — this is a guided data-collection prototype, not a live integration with any provider.

---

## Limitations

1. **Knowledge cutoff:** The knowledge base reflects the state of CPS Energy, SAWS, and City of SA websites at the time the SA Utilities pipeline was last run (`make download-data`). Rates, fees, and policies change. Users should verify current information directly with providers before making financial decisions.

2. **Three providers only:** The assistant has no knowledge of services beyond CPS Energy, SAWS, and CoSA Solid Waste. Questions about internet, phone, cable, gas-only providers, or services outside San Antonio city limits will receive a "not found" response.

3. **Forms are not submitted:** The form workflows collect data locally and display a summary. They do not transmit any data to CPS Energy, SAWS, or the City of San Antonio. Users must take the completed information to the provider's actual website or phone line.

4. **English only:** All prompts, form labels, and responses are in English. Non-English input may produce degraded responses.

5. **LLM hallucination risk:** When the retrieval system returns low-confidence results, the LLM may produce answers not grounded in the knowledge base despite the citation policy. The system prompt instructs the model to say "I don't know" rather than hallucinate, but this is not guaranteed.

6. **Demo mode degradation:** Without an LLM API key, the system falls back to a rule-based stub that summarizes raw retrieval results without conversational polish. Form workflows and checklist features still work normally.

7. **Single-user sessions:** The system persists one `user_state.json` file per deployment. It is not designed for concurrent multi-user access.

---

## Risks

1. **PII collection:** The form workflows collect name, address, date of birth, phone, email, and masked SSN/driver license. This data is stored locally in `output/user_state.json`. Operators must not expose this file publicly. The container runs as a non-root user and the output directory is excluded from version control.

2. **Financial misinformation:** Incorrect deposit amounts, lead times, or fee information could lead users to underprepare financially. Every factual claim must include an inline citation (enforced in the system prompt); users should treat responses as a starting point, not a binding quote.

3. **Form errors not caught:** The system validates field formats (email, phone, ZIP, date, SSN shape) but does not verify whether the submitted values are correct (e.g., it cannot verify that the provided address is within CPS Energy's service territory). Incorrect values will propagate to the final review summary without error.

4. **Provider website changes:** The SA Utilities pipeline fetches and chunks provider websites. If a provider changes its URL structure or significantly restructures its content, the knowledge base will become stale until the pipeline is re-run.

5. **Injection via retrieval:** Retrieved web content is passed directly into LLM context. If a provider's website were compromised to contain adversarial text, it could influence LLM responses. Mitigation: the system prompt explicitly instructs the model to only use retrieved content for factual grounding.

---

## Out of Scope

The following uses are explicitly not supported and should not be attempted:

- **Live form submission:** The system does not and must not be modified to submit form data to any provider's API or website without explicit user consent and proper OAuth/identity verification.
- **Multi-tenant production deployment:** The single-file user state is not appropriate for production use with multiple simultaneous users. A database-backed session store would be required.
- **Legal or financial advice:** The assistant is not a licensed financial advisor. Deposit waiver eligibility (military, domestic violence survivor programs) should be verified with the provider directly.
- **Services outside San Antonio:** The knowledge base covers CPS Energy, SAWS, and CoSA only. The system should not be used to guide users setting up utilities in other cities.
- **Personal data analytics:** The `output/user_state.json` file and conversation history must not be used for any purpose other than providing the in-session user experience.
