"use client"

import React from "react"
import { Toaster as Sonner, type ToasterProps } from "sonner"
import { CheckCircle2, Info, AlertTriangle, XCircle, Loader2 } from "lucide-react"

// BUG-003 fix: Removed next-themes dependency — app is dark-only and has no ThemeProvider.
// useTheme() always returned "system" causing incorrect toast colors. Hardcoded "dark".
// BUG-014 fix: Added explicit React import for React.CSSProperties usage.

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="dark"
      className="toaster group"
      icons={{
        success: (
          <CheckCircle2 className="size-4" />
        ),
        info: (
          <Info className="size-4" />
        ),
        warning: (
          <AlertTriangle className="size-4" />
        ),
        error: (
          <XCircle className="size-4" />
        ),
        loading: (
          <Loader2 className="size-4 animate-spin" />
        ),
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
