import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"

interface CriticalFieldWarningModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title?: string
  body?: string
}

export function CriticalFieldWarningModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  body
}: CriticalFieldWarningModalProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[425px] bg-background border-red-500/20 shadow-lg shadow-red-500/10">
        <DialogHeader>
          <DialogTitle className="text-red-500">{title || "Critical Change Warning"}</DialogTitle>
          <DialogDescription className="text-muted-foreground pt-2 text-sm leading-relaxed">
            {body || "This change requires additional review because it affects critical business information."}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="mt-4 gap-2 sm:gap-0">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={onConfirm}>
            I Understand, Proceed
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
