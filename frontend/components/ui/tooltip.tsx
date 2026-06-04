"use client"

// @base-ui/react/tooltip exports a single `Tooltip` object with sub-components:
// Tooltip.Provider, Tooltip.Root, Tooltip.Trigger, Tooltip.Portal,
// Tooltip.Positioner, Tooltip.Popup, Tooltip.Arrow
import { Tooltip } from "@base-ui/react/tooltip"

import { cn } from "@/lib/utils"

function TooltipProvider({
  delay = 0,
  ...props
}: Tooltip.Provider.Props) {
  return (
    <Tooltip.Provider
      data-slot="tooltip-provider"
      delay={delay}
      {...props}
    />
  )
}

function TooltipRoot({ ...props }: Tooltip.Root.Props) {
  return <Tooltip.Root data-slot="tooltip" {...props} />
}

function TooltipTrigger({ ...props }: Tooltip.Trigger.Props) {
  return <Tooltip.Trigger data-slot="tooltip-trigger" {...props} />
}

function TooltipContent({
  className,
  side = "top",
  sideOffset = 4,
  align = "center",
  alignOffset = 0,
  children,
  ...props
}: Tooltip.Popup.Props &
  Pick<
    Tooltip.Positioner.Props,
    "align" | "alignOffset" | "side" | "sideOffset"
  >) {
  return (
    <Tooltip.Portal>
      <Tooltip.Positioner
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
        className="isolate z-50"
      >
        <Tooltip.Popup
          data-slot="tooltip-content"
          className={cn(
            "z-50 inline-flex w-fit max-w-xs items-center gap-1.5 rounded-md bg-foreground px-3 py-1.5 text-xs text-background",
            className
          )}
          {...props}
        >
          {children}
          <Tooltip.Arrow className="z-50 size-2.5 translate-y-[calc(-50%-2px)] rotate-45 rounded-[2px] bg-foreground fill-foreground" />
        </Tooltip.Popup>
      </Tooltip.Positioner>
    </Tooltip.Portal>
  )
}

export { TooltipRoot as Tooltip, TooltipTrigger, TooltipContent, TooltipProvider }
