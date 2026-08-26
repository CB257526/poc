import { Navigate, Route, Routes } from "react-router-dom";
import { GuestOnly, RequireAuth } from "./auth/guards";
import { AppLayout } from "./layout/AppLayout";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { ConfigPage } from "./pages/ConfigPage";
import { ExportsPage } from "./pages/ExportsPage";
import { LoginPage } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ProcessingPage } from "./pages/ProcessingPage";
import { QuotesPage } from "./pages/QuotesPage";
import { RegisterPage } from "./pages/RegisterPage";
import { UsersPage } from "./pages/UsersPage";

export default function App() {
  return (
    <Routes>
      <Route element={<GuestOnly />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/processing" element={<ProcessingPage />} />
          <Route path="/quotes" element={<QuotesPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/exports" element={<ExportsPage />} />
          <Route path="/config" element={<ConfigPage />} />
          <Route path="/users" element={<UsersPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
