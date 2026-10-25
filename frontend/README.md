# CareRelay Clinic Command Console

The CareRelay frontend: a React + TypeScript single-page application that
gives clinic staff a live view into every patient prior-authorization case,
including the full Strands multi-agent reasoning trace behind each decision.

This is the second of CareRelay's two interfaces. Patients never see this -
they interact entirely over WhatsApp/RCS (AWS End User Messaging), which is
the whole point of CareRelay's channel design. This console is for clinic
staff, and it exists specifically to make the "code decides, AI talks"
architecture visible and auditable: every prior-auth outcome shown here
traces to a specific row in the deterministic rules table, never to an LLM
guess.

## Views

- **Intake Queue** (`/`) - live, filterable, searchable list of all cases.
- **Case Detail** (`/cases/:id`) - the full Strands agent trace (Intake ->
  Verification -> Notification) rendered as a visual pipeline, the
  deterministic rule citation, the extracted insurance card fields, the
  simulated payer IVR result, and live previews of the exact WhatsApp
  patient message / RCS doctor card / SES audit email that were sent.
- **Rule Explorer** (`/rules`) - browse the deterministic payer/CPT rule
  table directly, independent of any case, so the underlying logic is
  auditable as data.
- **Analytics** (`/analytics`) - outcome breakdown, most-missing documents,
  channel mix, and payer-simulation eligibility rate.

## Running it

### Zero-setup demo mode (no AWS required)

```bash
npm install
npm run dev
```

Open `http://localhost:5173`. The app defaults to **mock data** (five
realistic cases covering every outcome) whenever no API endpoint is
configured, so it's fully demo-able out of the box.

### Against your deployed backend

1. Deploy the CDK stacks (`cdk deploy --all`) and copy the
   **`DashboardApiUrl`** stack output.
2. In the app, click **Configure endpoint** in the sidebar, switch to
   **Live API**, and paste the URL.
3. Or set it at build time via an env file:

   ```bash
   # frontend/.env.local
   VITE_API_BASE_URL=https://xxxx.execute-api.ap-south-1.amazonaws.com/prod
   ```

The data-source choice is saved to `localStorage`, so you only configure it
once.

## Build

```bash
npm run build     # type-checks (tsc -b) then builds to dist/
npm run lint       # ESLint
npm run preview    # serve the production build locally
```

## Stack

React 18 + TypeScript + Vite, TanStack Query for data fetching/polling
(5s interval), React Router for client-side routing, Tailwind CSS for
styling, Recharts for the analytics charts.

## Security note

The backing `dashboard_api` is deployed unauthenticated by default so this
console works with zero setup (see `docs/DASHBOARD.md` in the repo root).
It is read-only and never returns raw patient phone numbers (pre-masked at
write time). Add an authorizer before any real deployment.
