"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownRendererProps {
  content: string;
}

/*
 * Custom renderers — defined at module level (NOT inside the component) to
 * keep the same JSX function references across renders, per the
 * `rerender-no-inline-components` rule.
 *
 * Tailwind v4 + earth-tone palette: tokens like `text-foreground`,
 * `text-muted-foreground`, and `border-border` adapt to the theme so we don't
 * hardcode colors here.
 *
 * We intentionally don't use `prose`/typography plugin styles for these
 * because Claude's output uses very specific shapes (day headers, ferry
 * lines, ASCII sparklines) that look better with explicit Tailwind classes.
 */
const components: Components = {
  h1: ({ children }) => (
    <h1 className="mb-3 mt-2 text-xl font-semibold tracking-tight text-foreground first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2 mt-5 text-base font-semibold tracking-tight text-foreground first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-2 mt-4 text-sm font-semibold uppercase tracking-wider text-muted-foreground first:mt-0">
      {children}
    </h3>
  ),
  p: ({ children }) => (
    <p className="mb-2 text-sm leading-relaxed text-foreground/90 last:mb-0">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="mb-3 ml-5 list-disc space-y-1.5 text-sm leading-relaxed marker:text-muted-foreground/60">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-3 ml-5 list-decimal space-y-1.5 text-sm leading-relaxed marker:text-muted-foreground/80 marker:font-medium">
      {children}
    </ol>
  ),
  // Use the browser's native list marker (• for ul, 1. for ol) so we don't
  // double up on bullet characters when the agent uses an ordered list.
  li: ({ children }) => (
    <li className="pl-1 text-foreground/90 [&>strong]:text-foreground">{children}</li>
  ),
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  em: ({ children }) => <em className="not-italic font-semibold text-foreground/90">{children}</em>,
  hr: () => <hr className="my-4 border-border/50" />,
  code: ({ children }) => (
    <code className="rounded bg-card px-1.5 py-0.5 font-mono text-[0.85em] text-primary">
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className="my-3 overflow-x-auto rounded-md border border-border/40 bg-card/60 px-3 py-2 font-mono text-xs leading-relaxed">
      {children}
    </pre>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-primary/40 bg-primary/5 px-3 py-2 text-sm text-foreground/85">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-b border-border/40 px-2 py-1.5 text-left font-medium text-muted-foreground">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-b border-border/20 px-2 py-1.5 text-foreground/90">{children}</td>
  ),
};

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {content}
    </ReactMarkdown>
  );
}
