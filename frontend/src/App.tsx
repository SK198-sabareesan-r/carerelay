import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Login } from "./views/Login";
import { Signup } from "./views/Signup";
import { IntakeQueue } from "./views/IntakeQueue";
import { CaseDetailView } from "./views/CaseDetailView";
import { RuleExplorer } from "./views/RuleExplorer";
import { Analytics } from "./views/Analytics";
import { isSignedIn } from "./lib/auth";

function RequireAuth({ children }: { children: React.ReactElement }) {
  if (!isSignedIn()) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />

        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          {/* Analytics is the landing/home page after sign-in. */}
          <Route index element={<Navigate to="/analytics" replace />} />
          <Route path="analytics" element={<ErrorBoundary><Analytics /></ErrorBoundary>} />
          <Route path="queue" element={<ErrorBoundary><IntakeQueue /></ErrorBoundary>} />
          <Route path="cases/:caseId" element={<ErrorBoundary><CaseDetailView /></ErrorBoundary>} />
          <Route path="rules" element={<ErrorBoundary><RuleExplorer /></ErrorBoundary>} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
