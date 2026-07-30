import React, { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import confetti from "canvas-confetti";

interface ConfettiCelebrationProps {
  show: boolean;
}

export default function ConfettiCelebration({
  show,
}: ConfettiCelebrationProps) {
  useEffect(() => {
    if (show) {
      confetti({
        particleCount: 150,
        spread: 70,
        origin: { y: 0.6 },
        colors: ["#00f5a0", "#8b5cf6", "#3b82f6", "#f59e0b"],
      });
    }
  }, [show]);

  return (
    <AnimatePresence>
      {show && (
        <div className="absolute inset-0 z-[100] pointer-events-none flex items-center justify-center backdrop-blur-[2px]">
          <motion.div
            initial={{ scale: 0.5, opacity: 0, y: 50 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 1.5, opacity: 0, filter: "blur(10px)" }}
            className="px-12 py-8 bg-gradient-to-br from-[#0c1a15]/90 to-black/90 border-2 border-[#00f5a0] rounded-xl shadow-[0_0_100px_rgba(0,245,160,0.4)] flex flex-col items-center gap-4"
          >
            <div className="text-[#00f5a0] text-7xl drop-shadow-[0_0_20px_rgba(0,245,160,0.8)]">
              ✨💰✨
            </div>
            <h1 className="text-6xl font-black text-transparent bg-clip-text bg-gradient-to-r from-[#00f5a0] to-emerald-300 tracking-tighter uppercase drop-shadow-[0_0_15px_rgba(0,245,160,0.6)]">
              BAG SECURED
            </h1>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
