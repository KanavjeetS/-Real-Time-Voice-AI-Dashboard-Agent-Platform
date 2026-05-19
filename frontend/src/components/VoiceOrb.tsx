"use client";

import { motion } from "framer-motion";

/** Animated voice orb — Google AI Studio glass style */
export function VoiceOrb({ active = false, size = "lg" }: { active?: boolean; size?: "sm" | "lg" }) {
  const wrap = size === "lg" ? "w-40 h-40" : "w-24 h-24";
  const core = size === "lg" ? "w-32 h-32" : "w-16 h-16";

  return (
    <div className={`relative ${wrap} flex items-center justify-center`} aria-hidden>
      <motion.div
        className="absolute inset-0 rounded-full bg-indigo-500/30 blur-3xl"
        animate={
          active
            ? { scale: [1, 1.15, 1], opacity: [0.35, 0.55, 0.35] }
            : { scale: 1, opacity: 0.25 }
        }
        transition={{ duration: 2.5, repeat: active ? Infinity : 0, ease: "easeInOut" }}
      />
      <motion.div
        className={`relative ${core} flex items-center justify-center rounded-full border border-white/20 bg-gradient-to-br from-indigo-500 via-indigo-600 to-violet-700 shadow-[0_0_48px_rgba(99,102,241,0.45)]`}
        animate={active ? { scale: [1, 1.03, 1] } : {}}
        transition={{ duration: 1.2, repeat: active ? Infinity : 0 }}
      >
        <motion.div className="flex items-end justify-center gap-1 pb-2">
          {[4, 7, 5, 9, 6, 8, 4].map((h, i) => (
            <motion.span
              key={i}
              className="w-1 min-h-[4px] rounded-full bg-white/90"
              animate={
                active
                  ? { height: [`${h * 2}px`, `${h * 4}px`, `${h * 2}px`] }
                  : { height: "8px" }
              }
              transition={{
                duration: 0.6,
                repeat: active ? Infinity : 0,
                delay: i * 0.08,
                ease: "easeInOut",
              }}
            />
          ))}
        </motion.div>
      </motion.div>
      {active && size === "lg" && (
        <motion.span
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className="absolute -bottom-3 left-1/2 -translate-x-1/2 text-[10px] font-bold uppercase tracking-[0.25em] text-emerald-400"
        >
          Live
        </motion.span>
      )}
    </div>
  );
}
