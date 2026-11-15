import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  BriefcaseBusiness,
  CalendarDays,
  HelpCircle,
  Home,
  LogIn,
  LogOut,
  User,
} from "lucide-react";
import { logoutUser, getSession } from "../lib/jobseekerProfile";

const NAV = [
  { Icon: Home, to: "/", label: "Home" },
  { Icon: CalendarDays, to: "/calendar", label: "Calendar" },
  { Icon: HelpCircle, to: "/help", label: "Help" },
  { Icon: User, to: "/profile", label: "Profile" },
];

export default function Header() {
  const location = useLocation();
  const navigate = useNavigate();
  const [, setTick] = useState(0);

  useEffect(() => {
    const bump = () => setTick((n) => n + 1);
    window.addEventListener("jobseeker-session-changed", bump);
    return () => window.removeEventListener("jobseeker-session-changed", bump);
  }, []);

  const session = getSession();

  function logout() {
    logoutUser();
    navigate("/");
  }

  return (
    <header className="relative z-10 flex items-center justify-between bg-white px-8 py-5 shadow-sm">
      <Link to="/" className="flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-teal-700 text-white shadow-md">
          <BriefcaseBusiness size={25} />
        </div>
        <span className="text-3xl font-bold tracking-tight text-slate-900">JobPilot</span>
      </Link>

      <nav className="absolute left-1/2 top-5 flex -translate-x-1/2 gap-4" aria-label="Main menu">
        {NAV.map(({ Icon, to, label }) => {
          const active =
            to === "/"
              ? location.pathname === "/"
              : location.pathname === to || location.pathname.startsWith(`${to}/`);
          return (
            <Link
              key={to}
              to={to}
              title={label}
              className={`flex h-14 w-14 items-center justify-center rounded-full shadow-lg transition hover:scale-105 ${
                active ? "bg-teal-900 ring-2 ring-teal-400" : "bg-teal-700 hover:bg-teal-800"
              } text-white`}
            >
              <Icon size={25} />
            </Link>
          );
        })}
      </nav>

      <div className="flex flex-col items-end gap-1">
        {session?.email ? (
          <span className="max-w-[220px] truncate text-xs font-semibold text-slate-600" title={session.email}>
            {session.email}
          </span>
        ) : null}
        <button
          type="button"
          className="flex items-center gap-2 rounded-md bg-teal-700 px-5 py-3 font-bold text-white shadow-sm hover:bg-teal-800"
          onClick={() => (session?.email ? logout() : navigate("/login"))}
        >
          {session?.email ? <LogOut size={18} /> : <LogIn size={18} />}
          {session?.email ? "Log out" : "Log in"}
        </button>
      </div>
    </header>
  );
}
