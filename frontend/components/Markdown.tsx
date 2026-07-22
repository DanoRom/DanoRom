/**
 * Minimal markdown renderer (headings, lists, bold, inline code, paragraphs).
 * Kept dependency-free per the no-extra-cost / permissive-license rules.
 */

import { Fragment, ReactNode } from "react";

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${keyPrefix}-${i}`}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={`${keyPrefix}-${i}`}>{part.slice(1, -1)}</code>;
    }
    return <Fragment key={`${keyPrefix}-${i}`}>{part}</Fragment>;
  });
}

export default function Markdown({ source }: { source: string }) {
  const blocks: ReactNode[] = [];
  let listItems: string[] = [];
  let key = 0;

  const flushList = () => {
    if (listItems.length) {
      blocks.push(
        <ul key={key++}>
          {listItems.map((item, i) => (
            <li key={i}>{renderInline(item, `li-${key}-${i}`)}</li>
          ))}
        </ul>
      );
      listItems = [];
    }
  };

  for (const raw of source.split("\n")) {
    const line = raw.trimEnd();
    const heading = line.match(/^(#{1,3})\s+(.*)/);
    const bullet = line.match(/^[-*]\s+(.*)/);

    if (bullet) {
      listItems.push(bullet[1]);
      continue;
    }
    flushList();

    if (heading) {
      const level = heading[1].length;
      const content = renderInline(heading[2], `h-${key}`);
      blocks.push(
        level === 1 ? (
          <h1 key={key++}>{content}</h1>
        ) : level === 2 ? (
          <h2 key={key++}>{content}</h2>
        ) : (
          <h3 key={key++}>{content}</h3>
        )
      );
    } else if (line.trim()) {
      blocks.push(<p key={key++}>{renderInline(line, `p-${key}`)}</p>);
    }
  }
  flushList();

  return <div>{blocks}</div>;
}
