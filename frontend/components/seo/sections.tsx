import Link from 'next/link'
import { canLink } from '@/lib/lpseo'

// Section primitives shared by the SEO page family (country pillar, city pillar,
// industry x city leaf, pSEO leaf). Each of these existed as a byte-identical copy
// inside three to five page components, so a fix to one silently missed the others.
//
// Server components: nothing here may become a client component, or every page in
// the family ships the runtime.

export const SectionHeading = ({ eyebrow, title, sub }: { eyebrow?: string; title: string; sub?: string }) => (
  <div className="mx-auto max-w-3xl space-y-3 text-center">
    {eyebrow && <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">{eyebrow}</div>}
    <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">{title}</h2>
    {sub && <p className="text-muted-foreground">{sub}</p>}
  </div>
)

export const Section = ({ id, eyebrow, title, sub, children, alt }: {
  id?: string; eyebrow?: string; title: string; sub?: string
  children?: React.ReactNode; alt?: boolean
}) => (
  <section id={id} className={alt ? 'border-y border-border/40 bg-muted/10 py-16' : 'py-16'}>
    <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6 lg:px-8">
      <SectionHeading eyebrow={eyebrow} title={title} sub={sub} />
      {children}
    </div>
  </section>
)

// SafeLink needs the set of published paths, which is per-page — hence a factory.
// `const SafeLink = makeSafeLink(livePaths)` keeps every existing call site as-is.
//
// Never render an anchor to a page that does not exist yet (guardrail: no links to
// planned pages). Unpublished destinations degrade to plain text.
export const makeSafeLink = (livePaths: Set<string>) => {
  // Named rather than a bare arrow so react/display-name is satisfied.
  const SafeLink = ({ href, className, children }: { href: string; className?: string; children: React.ReactNode }) =>
    canLink(href, livePaths)
      ? <Link href={href} className={className}>{children}</Link>
      : <span className={className} aria-disabled>{children}</span>
  return SafeLink
}
