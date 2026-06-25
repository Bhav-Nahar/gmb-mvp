import { revalidatePath } from 'next/cache';
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
    const { slug } = body;

    if (!slug) {
      return Response.json({ error: "Missing slug" }, { status: 400 });
    }

    // Revalidate the single-level microsite page route
    revalidatePath(`/${slug}`);
    
    return Response.json({ revalidated: true });
  } catch (err) {
    console.error("Error in revalidation route:", err);
    return Response.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
