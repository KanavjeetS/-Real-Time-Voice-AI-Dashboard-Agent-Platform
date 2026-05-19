"use client";

import { motion } from "framer-motion";
import { Mic } from "lucide-react";

export function SplashScreen() {
  return (
    <motion.div
      initial={{ opacity: 1 }}
      exit={{ opacity: 0, scale: 1.02 }}
      transition={{ duration: 0.6, ease: "easeInOut" }}
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center overflow-hidden bg-[#030303]"
    >
      <motion.div
        className="absolute inset-0 bg-gradient-to-t from-indigo-500/10 to-transparent"
        animate={{ opacity: [0.5, 0.8, 0.5] }}
        transition={{ duration: 3, repeat: Infinity }}
      />
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8 }}
        className="z-10 flex flex-col items-center gap-8"
      >
        <motion.div className="relative">
          <motion.div
            animate={{ scale: [1, 1.2, 1], opacity: [0.3, 0.6, 0.3] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            className="absolute inset-0 rounded-full bg-indigo-500 blur-2xl"
          />
          <motion.div
            className="relative flex h-20 w-20 items-center justify-center rounded-2xl border border-white/20 bg-indigo-600 shadow-2xl"
            animate={{ rotate: [0, 2, -2, 0] }}
            transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
          >
            <Mic className="h-10 w-10 text-white" />
          </motion.div>
        </motion.div>
        <div className="space-y-2 text-center">
          <h1 className="text-3xl font-bold tracking-tighter text-white">AI CALLING AGENT</h1>
          <motion.div
            className="flex items-center justify-center gap-3"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
          >
            <span className="h-px w-12 bg-indigo-500/30" />
            <p className="text-[10px] font-bold uppercase tracking-[0.3em] text-zinc-500">Neural Voice Interface</p>
            <span className="h-px w-12 bg-indigo-500/30" />
          </motion.div>
        </div>
        <div className="mt-8 flex flex-col items-center gap-4">
          <div className="relative h-0.5 w-48 overflow-hidden rounded-full bg-white/5">
            <motion.div
              initial={{ x: "-100%" }}
              animate={{ x: "100%" }}
              transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
              className="absolute inset-0 w-full bg-gradient-to-r from-transparent via-indigo-500 to-transparent"
            />
          </div>
          <motion.p
            animate={{ opacity: [0.4, 1, 0.4] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="text-[10px] font-bold uppercase tracking-widest text-indigo-400"
          >
            Connecting to voice gateway…
          </motion.p>
        </div>
      </motion.div>
    </motion.div>
  );
}
