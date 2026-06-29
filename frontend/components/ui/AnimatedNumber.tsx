"use client";

import { useEffect, useState, useRef } from "react";

interface AnimatedNumberProps {
  value: number;
  duration?: number; // ms
  formatter?: (val: number) => string;
  isFloat?: boolean;
}

export function AnimatedNumber({
  value,
  duration = 1000,
  formatter = (val) => val.toLocaleString(),
  isFloat = false,
}: AnimatedNumberProps) {
  const [displayValue, setDisplayValue] = useState(0);
  const prevValue = useRef(0);

  useEffect(() => {
    let startTimestamp: number | null = null;
    const startValue = prevValue.current;
    
    // If value hasn't changed, just display it
    if (startValue === value) {
      setDisplayValue(value);
      return;
    }

    const step = (timestamp: number) => {
      if (!startTimestamp) startTimestamp = timestamp;
      const progress = Math.min((timestamp - startTimestamp) / duration, 1);
      
      // Easing function: easeOutExpo
      const easeProgress = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      
      const current = isFloat 
        ? startValue + (value - startValue) * easeProgress
        : Math.floor(startValue + (value - startValue) * easeProgress);
      setDisplayValue(current);

      if (progress < 1) {
        window.requestAnimationFrame(step);
      } else {
        setDisplayValue(value);
        prevValue.current = value;
      }
    };

    window.requestAnimationFrame(step);
  }, [value, duration]);

  return <span>{formatter(displayValue)}</span>;
}
