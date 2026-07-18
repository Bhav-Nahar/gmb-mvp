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
    const { slug, paths, pseoSlug } = body;

    // Three callers:
    //  - microsites send { slug } -> revalidate the single-level /{slug} route
    //  - pSEO publish/import sends { paths: [...] } -> global 'pseo' tag + each path
    //  - pSEO per-page flush sends { pseoSlug, paths } -> ONLY that page's tag +
    //    path, leaving every other pSEO page's cache (HTML + data) intact.
    if (typeof pseoSlug === 'string' && pseoSlug) {
      revalidateTag(`pseo:${pseoSlug}`);
      for (const p of Array.isArray(paths) ? paths : []) {
        if (typeof p === 'string' && p.startsWith('/')) revalidatePath(p);
      }
      return Response.json({ revalidated: true, scope: pseoSlug });
    }

    if (Array.isArray(paths) && paths.length > 0) {
      // The 'pseo' tag on the lib/pseo.ts fetches busts all pSEO data at once;
      // revalidatePath then purges the ISR HTML for the affected leaf + hubs.
      revalidateTag('pseo');
      for (const p of paths) {
        if (typeof p === 'string' && p.startsWith('/')) revalidatePath(p);
      }
      return Response.json({ revalidated: true, count: paths.length });
    }

    if (!slug) {
      return Response.json({ error: "Missing slug or paths" }, { status: 400 });
    }

    revalidatePath(`/${slug}`);
    return Response.json({ revalidated: true });
  } catch (err) {
    console.error("Error in revalidation route:", err);
    return Response.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
