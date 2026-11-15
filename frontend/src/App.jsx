import { HashRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useEffect } from "react";
import { fetchProfileFromServer, getProfilePayload, getToken } from "./lib/jobseekerProfile";
import Footer from "./portal/Footer";
import Header from "./portal/Header";
import HomePage from "./portal/HomePage";
import LoginPage from "./portal/LoginPage";
import NewOfferPage from "./portal/NewOfferPage";
import OfferReplyPage from "./portal/OfferReplyPage";
import ProfilePage from "./portal/ProfilePage";
import PlaceholderPage from "./portal/PlaceholderPage";
import ResumeChatPage from "./portal/ResumeChatPage";
import ResumeViewPage from "./portal/ResumeViewPage";
import SavedCompaniesPage from "./portal/SavedCompaniesPage";

function PortalShell() {
  useEffect(() => {
    if (!getToken()) return;
    if (!getProfilePayload()) {
      fetchProfileFromServer().catch(() => {});
      return;
    }
    const timer = window.setTimeout(() => {
      fetchProfileFromServer().catch(() => {});
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="relative min-h-screen bg-slate-50 text-slate-900">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_left,rgba(15,118,110,0.12),transparent_35%),linear-gradient(90deg,rgba(15,23,42,0.06)_0,transparent_18%)]" />
      <Header />
      <div className="relative z-10">
        <Outlet />
      </div>
      <Footer />
    </div>
  );
}

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<PortalShell />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/new" element={<NewOfferPage />} />
          <Route path="/new/reply" element={<OfferReplyPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/resume/create" element={<ResumeChatPage />} />
          <Route path="/resume/view" element={<ResumeViewPage />} />
          <Route
            path="/calendar"
            element={<PlaceholderPage title="Calendar" hint="Deadlines and reminders will appear here later." />}
          />
          <Route
            path="/help"
            element={
              <PlaceholderPage
                title="Help"
                hint="Open /docs for OpenAPI. Slim build: resume, score, safe tailoring."
              />
            }
          />
          <Route path="/saved" element={<SavedCompaniesPage />} />
        </Route>

        <Route path="/applications" element={<Navigate to="/" replace />} />
        <Route path="/applications/*" element={<Navigate to="/" replace />} />
        <Route path="/new/wizard" element={<Navigate to="/new" replace />} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </HashRouter>
  );
}
