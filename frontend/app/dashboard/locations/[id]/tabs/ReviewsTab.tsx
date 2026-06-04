import ReviewsPage from "../../../reviews/page"

interface ReviewsTabProps {
  locationId: number
}

export function ReviewsTab({ locationId }: ReviewsTabProps) {
  return (
    <div className="animate-in fade-in duration-500">
      <ReviewsPage locationId={locationId} />
    </div>
  )
}
