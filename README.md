<div align="center">

# 💰 Finance Overdue Agent

### An AI Agent That Automatically Follows Up on Overdue Invoices


[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)]()
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent%20Workflow-8A2BE2)]()
[![Mistral AI](https://img.shields.io/badge/Mistral-AI-orange)]()
[![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-red?logo=streamlit)]()
[![License](https://img.shields.io/badge/License-MIT-green)]()

</div>

---

## What This Project Does

Finance teams spend hours every week chasing overdue invoices — tracking due dates, writing reminder emails, escalating risky accounts, and logging everything for audits.

This agent does that job automatically. You upload a CSV of invoices, and it:

- Figures out how overdue each invoice is
- Writes a follow-up email with the right tone for that stage
- Checks the email for correctness before anything goes out
- Waits for a human to approve or reject it
- Sends the approved email and logs the whole thing
- Escalates seriously overdue accounts to a manager
- Retries anything that failed, automatically

Everything is traceable — every invoice, every email, every decision is logged.


---

## How It Works (Simple Version)

1. **Upload** a CSV of invoices through the dashboard
2. **The agent reads each invoice** and works out how many days overdue it is
3. **It picks a stage** — from a friendly first reminder to a final notice
4. **It writes an email** using an LLM (Mistral AI), matching the tone to the stage
5. **It double-checks the email** against hard business rules (correct amount, correct invoice number, no missing details)
6. **A human reviews it** — approve to send, or reject with feedback so the agent rewrites it
7. **It logs everything** to a database and sends a trace to LangSmith for full visibility
8. **If something fails**, it's queued and retried automatically later

Behind the scenes, this flow is built as a graph of steps using LangGraph, so each stage (draft, validate, approve, send, log) is a clear, separate, testable node — not one giant tangled function.

---

## The 5 Follow-Up Stages

- **Not yet due** → no email sent
- **1–7 days overdue** → warm, friendly reminder
- **8–14 days overdue** → polite but firm follow-up
- **15–21 days overdue** → formal notice, response required
- **22–30 days overdue** → stern final notice before collections
- **31+ days overdue** → flagged for manual finance/legal escalation

---

## Key Features

**AI-Powered Emails**
- Tone automatically matches how overdue the invoice is
- Structured, validated output — no free-form guessing from the LLM
- Payment links inserted automatically

**Agentic Workflow**
- Built with LangGraph: a main orchestration flow plus a per-invoice worker flow
- Automatic retries and validation loops
- Can recover from where it left off if interrupted

**Human-in-the-Loop**
- Nothing gets sent without approval
- Rejected drafts go back for a rewrite, using the reviewer's feedback

**Dashboard**
- Upload invoices and see live job status
- Browse audit logs, email logs, and failed invoices
- Everything visible in one Streamlit app

**Built for Reliability**
- Every action is logged to a database with a full audit trail
- Duplicate uploads are automatically detected and skipped
- Personal data is masked in logs
- Failed jobs retry automatically with backoff, instead of just disappearing

---

## Under the Hood

Beyond the core workflow, this project also includes:

- **Semantic memory** — the agent remembers past interactions with a client (using a vector database, Qdrant) so it can bring relevant history into a new email instead of starting from scratch every time
- **Risk scoring** — a dedicated step calculates a real risk score with a formula (not the LLM's guess) before deciding whether an account needs escalation
- **Fact verification** — before an email is approved, a separate check confirms the amount, dates, and invoice number in the draft actually match the real invoice data
- **Tool integrations (MCP)** — the agent can call out to real tools like Outlook, Slack, Google Sheets, Jira, SAP, and a CRM, using a standardized, swappable interface

---

## Tech Stack

- **LLM:** Mistral AI
- **Agent orchestration:** LangGraph + LangChain
- **Memory / RAG:** Qdrant (vector database)
- **Output validation:** Pydantic
- **Dashboard:** Streamlit
- **Database:** SQLite
- **Scheduled retries:** APScheduler
- **Observability:** LangSmith
- **Config:** python-dotenv

---

## Project Structure

    finance-overdues-agent/
        app.py                  → Streamlit dashboard
        workflow.py              → main LangGraph orchestration
        invoice_workflow.py       → per-invoice worker flow
        agents/                    → risk scoring, fact verification
        mcp/                        → tool integrations (Outlook, Slack, CRM, etc.)
        memory/                       → semantic memory + RAG
        database/                      → jobs, audit logs, failed invoices
        vectorstore/                     → Qdrant client + embeddings
        data/uploads/                     → uploaded CSVs
        logs/                               → dry-run email logs
        requirements.txt
        .env.example

---


## Why This Project Matters

This isn't just a script that calls an LLM once — it's a full system:

- The AI never gets the final say on numbers or facts — those are always checked deterministically
- Every decision is logged and traceable, which is exactly how a finance tool needs to behave
- A human always approves before anything actually sends
- It fails gracefully — nothing silently disappears, everything retries or gets flagged

---

## Roadmap

- [ ] Real email delivery via SendGrid / Mailgun
- [ ] Direct ERP integrations (SAP, Oracle, Zoho Books)
- [ ] Role-based access control
- [ ] Multi-language emails
- [ ] PDF invoice attachments
- [ ] In-dashboard approve/reject buttons
- [ ] Collection trend analytics

---

## License

MIT License.

<div align="center">

</div>