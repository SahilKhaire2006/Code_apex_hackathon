"use client";

import { animate } from "framer-motion";
import { useEffect, useRef, useState } from "react";

interface AnimatedCounterProps {
  value: number;
  duration?: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
}

export function AnimatedCounter({
  value,
  duration = 1200,
  prefix = "",
  suffix = "",
  decimals = 0,
}: AnimatedCounterProps) {
  const [display, setDisplay] = useState<number>(0);
  const previousValue = useRef(0);

  useEffect(() => {
    const controls = animate(previousValue.current, value, {
      duration: duration / 1000,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (latest) => setDisplay(latest),
    });

    previousValue.current = value;

    return () => controls.stop();
  }, [duration, value]);

  return (
    <span className="font-mono text-(--text-primary)">
      {prefix}
      <span>{display.toFixed(decimals)}</span>
      {suffix}
    </span>
  );
}
