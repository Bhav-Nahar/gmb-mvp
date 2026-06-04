import PostsPage from "../../../posts/page"

interface PostsTabProps {
  locationId: number
}

export function PostsTab({ locationId }: PostsTabProps) {
  return (
    <div className="animate-in fade-in duration-500">
      <PostsPage locationId={locationId} />
    </div>
  )
}
