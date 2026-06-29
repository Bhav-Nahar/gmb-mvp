// Mirrors the backend ReplyTemplateService.resolve_variables aliases. Variables
// without a supplied value render to empty string (same as the backend) — NOT to
// sample data, so real reply paths never post placeholder text. The editor preview
// passes sample values via `opts` explicitly.
export function resolveTemplateVariables(
  body: string,
  reviewerName: string,
  locationName: string,
  opts?: { city?: string; phone?: string; website?: string; rating?: string }
): string {
  const firstName = (reviewerName || '').trim().split(' ')[0] || reviewerName;
  const replacements: Record<string, string> = {
    reviewer_name: reviewerName,
    customer: reviewerName,
    first_name: firstName,
    location_name: locationName,
    location: locationName,
    business: locationName,
    city: opts?.city ?? '',
    phone: opts?.phone ?? '',
    website: opts?.website ?? '',
    rating: opts?.rating ?? '',
  };
  return body.replace(/\{\{\s*(\w+)\s*\}\}/g, (match, name) =>
    name in replacements ? replacements[name] : match
  );
}
