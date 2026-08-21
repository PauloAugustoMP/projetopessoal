import { useEffect } from "react";
import {
  Navigate,
  Route,
  BrowserRouter as Router,
  Routes,
  useNavigate,
} from "react-router-dom";
import { isLoggedIn } from "./api/client";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();

  useEffect(() => {
    // The API client raises this when the refresh token is gone or rejected.
    function handleExpired() {
      navigate("/login", { replace: true });
    }
    window.addEventListener("session-expired", handleExpired);
    return () => window.removeEventListener("session-expired", handleExpired);
  }, [navigate]);

  if (!isLoggedIn()) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <DashboardPage />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}
