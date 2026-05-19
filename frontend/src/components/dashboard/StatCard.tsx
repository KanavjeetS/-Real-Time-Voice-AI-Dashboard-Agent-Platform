"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  sublabel?: string;
  active?: boolean;
}

export function StatCard({ icon: Icon, label, value, sublabel, active = false }: StatCardProps) {
  return (
    <motion.div
      whileHover={{ y: -4 }}
      className="glass-panel relative flex flex-col gap-2 overflow-hidden p-6 group"
    >
      {active && (
        <motion.div className="absolute top-0 right-0 p-2" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
        </motion.div>
      )}
      <motion.div
        className="w-fit rounded-lg bg-indigo-500/10 p-2 transition-colors group-hover:bg-indigo-500/20"
        whileHover={{ scale: 1.05 }}
      >
        <Icon className="h-5 w-5 text-indigo-400" />
      </motion.div>
      <motion.div className="mt-2" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
        <p className="text-sm font-medium text-zinc-400">{label}</p>
        <h3 className="mt-1 text-2xl font-bold tracking-tight text-white">{value}</h3>
        {sublabel && (
          <p className="mt-1 text-[10px] uppercase tracking-wider text-zinc-500">{sublabel}</p>
        )}
      </motion.div>
      <motion.div
        className="absolute -bottom-8 -right-8 h-24 w-24 rounded-full bg-indigo-500/5 blur-2xl transition-colors group-hover:bg-indigo-500/10"
        animate={{ scale: [1, 1.1, 1] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
      />
    </motion.div>
  );
}
