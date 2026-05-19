"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface TabButtonProps {
  id: string;
  label: string;
  icon: LucideIcon;
  active: boolean;
  onClick: (id: string) => void;
}

export function TabButton({ id, label, icon: Icon, active, onClick }: TabButtonProps) {
  return (
    <button
      type="button"
      onClick={() => onClick(id)}
      className={cn(
        "relative flex shrink-0 items-center gap-2 px-6 py-4 text-sm font-medium transition-all",
        active ? "text-indigo-400" : "text-zinc-500 hover:text-zinc-300"
      )}
    >
      <Icon className="h-4 w-4" />
      {label}
      {active && (
        <motion.div layoutId="tab-underline" className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-500" />
      )}
    </button>
  );
}
