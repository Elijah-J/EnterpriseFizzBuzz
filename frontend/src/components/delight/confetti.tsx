"use client";

import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useRef,
  useState,
} from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ConfettiHandle {
  /** Trigger a confetti burst from the center of the viewport. */
  fire: () => void;
}

interface Particle {
  id: number;
  x: number;
  y: number;
  size: number;
  color: string;
  rotation: number;
  velocityX: number;
  velocityY: number;
  shape: "square" | "circle";
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * Palette drawn from the Warm Precision token system — amber accent
 * and warm stone surface tones. No cold colors, neon, or high-saturation
 * values to maintain brand cohesion during the celebration visualization.
 */
const COLORS = [
  "var(--accent, #F59E0B)",
  "var(--accent-hover, #D97706)",
  "var(--text-secondary, #A8A29E)",
  "var(--surface-overlay, #44403C)",
  "var(--fizzbuzz-gold, #EAB308)",
  "#B45309",
  "#78716C",
];

const PARTICLE_COUNT = 50;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * CSS-only confetti burst for completion acknowledgment visualization.
 *
 * Renders 50 particles (a mix of tiny squares and circles) in amber and
 * warm stone colors. Each particle receives randomized velocity, rotation,
 * and gravity parameters applied via CSS custom properties and @keyframes.
 * No canvas, no WebGL — pure DOM elements with CSS transforms.
 *
 * Triggered programmatically via an imperative handle: the parent calls
 * `confettiRef.current.fire()` and the burst animates for 1.5 seconds
 * before self-cleaning from the DOM.
 */
export const Confetti = forwardRef<ConfettiHandle>(function Confetti(_, ref) {
  const [particles, setParticles] = useState<Particle[]>([]);
  const idCounter = useRef(0);

  const fire = useCallback(() => {
    const newParticles: Particle[] = [];
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      idCounter.current++;
      newParticles.push({
        id: idCounter.current,
        x: 50 + (Math.random() - 0.5) * 20,
        y: 50 + (Math.random() - 0.5) * 10,
        size: 4 + Math.random() * 6,
        color: COLORS[Math.floor(Math.random() * COLORS.length)],
        rotation: Math.random() * 360,
        velocityX: (Math.random() - 0.5) * 120,
        velocityY: -(40 + Math.random() * 80),
        shape: Math.random() > 0.5 ? "square" : "circle",
      });
    }
    setParticles(newParticles);

    // Clean up after animation completes
    setTimeout(() => setParticles([]), 1500);
  }, []);

  useImperativeHandle(ref, () => ({ fire }), [fire]);

  if (particles.length === 0) return null;

  return (
    <div
      className="fixed inset-0 z-[9999] pointer-events-none overflow-hidden"
      aria-hidden="true"
    >
      {particles.map((p) => (
        <span
          key={p.id}
          className={`absolute ${p.shape === "circle" ? "rounded-full" : "rounded-[1px]"}`}
          style={{
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: `${p.size}px`,
            height: `${p.size}px`,
            backgroundColor: p.color,
            transform: `rotate(${p.rotation}deg)`,
            animation: `confetti-fall 1.4s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards`,
            // Per-particle CSS custom properties for unique trajectories
            ["--confetti-vx" as string]: `${p.velocityX}px`,
            ["--confetti-vy" as string]: `${p.velocityY}px`,
            ["--confetti-rot" as string]: `${p.rotation + Math.random() * 720}deg`,
          }}
        />
      ))}

      <style>{`
        @keyframes confetti-fall {
          0% {
            opacity: 1;
            transform: translate(0, 0) rotate(0deg) scale(1);
          }
          100% {
            opacity: 0;
            transform: translate(var(--confetti-vx), calc(var(--confetti-vy) + 300px)) rotate(var(--confetti-rot)) scale(0.5);
          }
        }
      `}</style>
    </div>
  );
});
