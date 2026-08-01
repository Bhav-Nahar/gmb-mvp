"use client"

// A small "i" affordance that explains a metric or section in plain English.
// Built on the popover (not the tooltip) because a tooltip only opens on hover —
// `openOnHover` gives us the desktop hover, and the popover's native click/tap
// toggle covers touch devices where hover doesn't exist.
import { Popover } from "@base-ui/react/popover"
import { Info } from "lucide-react"

import { cn } from "@/lib/utils"

export function InfoHint({
  text,
  className,
  side = "top",
}: {
  text: string
  className?: string
  side?: "top" | "bottom" | "left" | "right"
}) {
  return (
    <Popover.Root>
      <Popover.Trigger
        openOnHover
        delay={200}
        aria-label="What does this mean?"
        // Cards are often clickable; the hint must not trigger the card.
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "inline-flex shrink-0 items-center justify-center rounded-full text-muted-foreground/60 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          className
        )}
      >
        <Info className="h-3.5 w-3.5" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side={side} sideOffset={6} className="isolate z-50">
          <Popover.Popup className="max-w-[260px] rounded-lg border border-border bg-popover px-3 py-2 text-xs font-normal leading-relaxed text-popover-foreground shadow-lg">
            {text}
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}
