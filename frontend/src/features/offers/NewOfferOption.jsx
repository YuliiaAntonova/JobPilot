import { motion } from "framer-motion";
import { ChevronRight, Lock } from "lucide-react";

export default function NewOfferOption({ icon: Icon, title, text, disabled, badge, onClick }) {
  return (
    <motion.button
      type="button"
      whileHover={!disabled ? { y: -3 } : {}}
      onClick={disabled ? undefined : onClick}
      className={`flex w-full items-center gap-7 rounded-lg border border-slate-200 bg-white p-5 text-left shadow-md transition ${
        disabled ? "cursor-not-allowed opacity-60" : "hover:shadow-xl"
      }`}
    >
      <div
        className={`flex h-24 w-24 shrink-0 items-center justify-center rounded-full shadow-inner ${
          disabled ? "bg-slate-100 text-slate-400" : "bg-slate-100 text-orange-600"
        }`}
      >
        <Icon size={46} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-2xl font-extrabold text-slate-950">{title}</h2>
          {badge ? (
            <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-black text-slate-500">{badge}</span>
          ) : null}
          {disabled ? <Lock size={18} className="text-slate-400" aria-hidden /> : null}
        </div>
        <p className="mt-3 text-lg font-bold leading-snug text-teal-700">{text}</p>
      </div>
      <ChevronRight size={34} className={`shrink-0 ${disabled ? "text-slate-300" : "text-slate-900"}`} />
    </motion.button>
  );
}
