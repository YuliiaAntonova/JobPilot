import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { BriefcaseBusiness, LogIn, UserPlus } from "lucide-react";
import { loginUser, registerUser } from "../lib/jobseekerProfile";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from || "/profile";

  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e) {
    e.preventDefault();
    const em = email.trim();
    if (!em) {
      setErr("Please enter your email.");
      return;
    }
    if (password.length < 6) {
      setErr("Password must be at least 6 characters.");
      return;
    }
    setErr("");
    setBusy(true);
    try {
      if (mode === "register") {
        await registerUser(em, password);
      } else {
        await loginUser(em, password);
      }
      navigate(from, { replace: true });
    } catch (ex) {
      setErr(String(ex.message || ex));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto mt-12 w-full max-w-lg px-4 pb-32">
      <div className="mb-8 text-center">
        <Link to="/" className="inline-flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-teal-700 text-white shadow-md">
            <BriefcaseBusiness size={25} />
          </div>
          <span className="text-2xl font-bold tracking-tight text-slate-900">JobPilot</span>
        </Link>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="rounded-xl border border-slate-200 bg-white p-8 shadow-lg"
      >
        <h1 className="text-center text-3xl font-black text-slate-950">
          {mode === "login" ? "Sign in" : "Create account"}
        </h1>
        <p className="mt-3 text-center text-sm font-semibold text-slate-600">
          Your account and resume profile are stored on the server (PostgreSQL). A local browser profile is imported on
          first sign-in.
        </p>

        <div className="mt-6 flex rounded-lg bg-slate-100 p-1">
          <button
            type="button"
            onClick={() => setMode("login")}
            className={`flex-1 rounded-md py-2 text-sm font-black ${mode === "login" ? "bg-white shadow" : "text-slate-600"}`}
          >
            Sign in
          </button>
          <button
            type="button"
            onClick={() => setMode("register")}
            className={`flex-1 rounded-md py-2 text-sm font-black ${mode === "register" ? "bg-white shadow" : "text-slate-600"}`}
          >
            Register
          </button>
        </div>

        <form onSubmit={submit} className="mt-8 space-y-5">
          <div>
            <label htmlFor="login-email" className="block text-sm font-black text-slate-700">
              Email
            </label>
            <input
              id="login-email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-300 px-4 py-3 text-base outline-none focus:border-teal-700"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label htmlFor="login-password" className="block text-sm font-black text-slate-700">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-300 px-4 py-3 text-base outline-none focus:border-teal-700"
              placeholder="at least 6 characters"
            />
          </div>

          {err ? (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-800">{err}</div>
          ) : null}

          <button
            type="submit"
            disabled={busy}
            className="flex w-full items-center justify-center gap-2 rounded-md bg-teal-700 px-5 py-4 text-lg font-black text-white shadow-sm hover:bg-teal-800 disabled:opacity-60"
          >
            {mode === "login" ? <LogIn size={22} /> : <UserPlus size={22} />}
            {busy ? "…" : mode === "login" ? "Sign in" : "Register"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm font-semibold text-slate-600">
          <Link to="/" className="text-teal-700 hover:text-teal-900">
            ← Back to home
          </Link>
        </p>
      </motion.div>
    </main>
  );
}