export function BillingSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="h-8 bg-muted rounded w-1/4 mb-4"></div>
      
      <div className="grid gap-6 md:grid-cols-2">
        <div className="border rounded-lg p-6 space-y-4">
          <div className="h-6 bg-muted rounded w-1/2"></div>
          <div className="h-4 bg-muted rounded w-3/4"></div>
          <div className="h-4 bg-muted rounded w-full mt-4"></div>
          <div className="h-4 bg-muted rounded w-5/6"></div>
        </div>

        <div className="border rounded-lg p-6 space-y-4">
          <div className="h-6 bg-muted rounded w-1/2"></div>
          <div className="h-4 bg-muted rounded w-3/4"></div>
          <div className="h-2 bg-muted rounded w-full mt-4"></div>
        </div>
      </div>
    </div>
  );
}
