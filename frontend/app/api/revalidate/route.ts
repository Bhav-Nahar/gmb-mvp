import { revalidatePath, revalidateTag } from 'next/cache';
import { timingSafeEqual } from 'crypto';

// Constant-time compare so the secret can't be recovered via response timing.
function secretsMatch(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ab.length !== bb.length) return false;
  return timingSafeEqual(ab, bb);
}

export async function POST(request: Request) {
  try {
    const secret = process.env.REVALIDATE_SECRET;
    
    if (!secret) {
      console.error("REVALIDATE_SECRET is not configured in the frontend environment.");
      return Response.json({ error: "Server misconfiguration" }, { status: 500 });
    }

    const providedSecret = request.headers.get('x-revalidate-secret');
    
    if (!providedSecret || !secretsMatch(providedSecret, secret)) {
      return Response.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await request.json();
    const { slug, paths, tags } = body;

    // Callers:
    //  - microsites send { slug } -> revalidate the single-level /{slug} route
    //  - pSEO/lpSEO send { tags: [...], paths: [...] } -> bust exactly those cache
    //    tags (per-slug '{type}:{slug}' + the shared '{type}-list') and each path.
    //    There is no global '{type}' tag, so a batch only ever touches the pages
    //    it names — never every other page's cache.
    if (Array.isArray(tags) && tags.length > 0) {
      for (const t of tags) if (typeof t === 'string' && t) revalidateTag(t);
      for (const p of Array.isArray(paths) ? paths : []) {
        if (typeof p === 'string' && p.startsWith('/')) revalidatePath(p);
      }
      return Response.json({ revalidated: true, tags: tags.length });
    }

    if (!slug) {
      return Response.json({ error: "Missing slug or tags" }, { status: 400 });
    }

    revalidatePath(`/${slug}`);
    return Response.json({ revalidated: true });
  } catch (err) {
    console.error("Error in revalidation route:", err);
    return Response.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
