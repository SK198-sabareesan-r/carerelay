# CareRelay Clinic Command Console

The CareRelay frontend: a React + TypeScript single-page application that
gives clinic staff a live, auditable view of every patient
prior-authorization case.

This is the operational cockpit for clinic staff. Patients never see it —
they interact entirely over WhatsApp (and doctors over RCS), which is the
whole point of CareRelay's channel design. The console exists to make the
"code decides, AI talks" architecture visible and auditable: every
prior-auth outcome shown here traces to a specific row in the deterministic
rules table, never to a language-model guess.

## Views

- **Analytics** (`/analytics`) — outcome breakdown, case lifecycle stages,
  most-missing documents, channel mix, and card-extraction confidence.
- **Intake Queue** (`/queue`) — a live, searchable, filterable list of all
  cases, grouped into clear lifecycle stages (Awaiting patient → Pending
  approval → Scheduled → Denied) with per-stage counts. The **Start
  follow-up** action launches the core workflow: staff enter the patient's
  WhatsApp number (with country code), the recommended procedure, the
  intended appointment time, and whether the patient is insured.
- **Case Detail** (`/cases/:id`) — four focused tabs:
  - **Conversations** — a real-time, WhatsApp-styled thread of exactly what
    the patient sent and received (text, voice notes, card photos), plus a
    staff reply composer and the doctor approval card.
  - **Payer emails** — the hospital ↔ payer email correspondence with
    timestamps.
  - **Processing log** — the step-by-step record of what happened to the
    case, with the deterministic rule citation highlighted.
  - **Timeline & evidence** — the case activity timeline, the extracted
    insurance-card fields, captured evidence, and the audit email.

## Running it

### Zero-setup demo mode (no AWS required)

```bash
npm install
npm run dev
```

Open `http://localhost:5173`. The app ships with realistic mock data
covering every outcome, so it's fully demo-able out of the box.

### Against your deployed backend

The build defaults to the live dashboard API, so a production build points
at the real backend automatically. To override the API base at build time:

```bash
# frontend/.env.local
VITE_API_BASE_URL=https://xxxx.execute-api.ap-south-1.amazonaws.com/prod
```

You can also switch between mock and live data from the **Configure
endpoint** control in the console; the choice is saved to `localStorage`.

## Build & deploy

```bash
npm run build      # type-checks (tsc -b) then builds to dist/
npm run lint       # ESLint
npm run preview    # serve the production build locally
```

The console is deployed to **AWS Amplify Hosting** via
`python scripts/deploy_frontend.py` from the repo root (builds and ships
`dist/` with automatic HTTPS and SPA routing).

## Stack

React 18 + TypeScript + Vite, TanStack Query for data fetching/polling
(live updates), React Router for routing, Tailwind CSS for styling,
Recharts for the analytics charts.

## Security note

The backing `dashboard_api` is unauthenticated by default so the console
works with zero setup. It never returns raw patient phone numbers (masked
at write time). Add an authorizer before any production deployment.
