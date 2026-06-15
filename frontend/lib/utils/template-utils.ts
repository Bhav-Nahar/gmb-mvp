export function resolveTemplateVariables(
  body: string,
  reviewerName: string,
  locationName: string
): string {
  const replacements: Record<string, string> = {
    reviewer_name: reviewerName,
    location_name: locationName,
  };
  return body.replace(/\{\{\s*(\w+)\s*\}\}/g, (match, name) =>
    name in replacements ? replacements[name] : match
  );
}
