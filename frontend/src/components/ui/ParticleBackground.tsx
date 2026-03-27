"use client";

import { useAnimationFrame } from "framer-motion";
import { useMemo, useRef } from "react";

interface Particle {
  x: number;
  y: number;
  size: number;
  speed: number;
  opacity: number;
}

interface ParticleBackgroundProps {
  count?: number;
}

function seededValue(seed: number) {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

export function ParticleBackground({ count = 36 }: ParticleBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const particles = useMemo<Particle[]>(
    () =>
      Array.from({ length: count }).map((_, idx) => ({
        x: seededValue(idx + 1),
        y: seededValue((idx + 1) * 3),
        size: seededValue((idx + 1) * 5) * 1.8 + 1,
        speed: seededValue((idx + 1) * 7) * 0.00006 + 0.00002,
        opacity: seededValue((idx + 1) * 11) * 0.4 + 0.2,
      })),
    [count],
  );

  useAnimationFrame(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const parent = canvas.parentElement;
    if (!parent) return;

    if (canvas.width !== parent.clientWidth || canvas.height !== parent.clientHeight) {
      canvas.width = parent.clientWidth;
      canvas.height = parent.clientHeight;
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    particles.forEach((particle) => {
      particle.y -= particle.speed;
      if (particle.y < -0.02) {
        particle.y = 1.02;
      }

      ctx.beginPath();
      ctx.fillStyle = `rgba(0, 212, 255, ${particle.opacity})`;
      ctx.arc(particle.x * canvas.width, particle.y * canvas.height, particle.size, 0, Math.PI * 2);
      ctx.fill();
    });
  });

  return <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />;
}
