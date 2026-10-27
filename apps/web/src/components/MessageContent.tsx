import { createMemo } from "solid-js";
import { marked } from "marked";
import DOMPurify from "dompurify";

/** Provider output is untrusted. Render Markdown only through a restrictive HTML boundary. */
export function MessageContent(props: { content: string }) {
  const html = createMemo(() =>
    DOMPurify.sanitize(
      marked.parse(props.content, { async: false, gfm: true }),
      {
        ALLOWED_TAGS: [
          "p",
          "br",
          "strong",
          "em",
          "del",
          "h1",
          "h2",
          "h3",
          "h4",
          "h5",
          "h6",
          "ul",
          "ol",
          "li",
          "blockquote",
          "pre",
          "code",
          "a",
          "hr",
          "table",
          "thead",
          "tbody",
          "tr",
          "th",
          "td",
        ],
        ALLOWED_ATTR: ["href", "title", "start"],
        ALLOW_DATA_ATTR: false,
      },
    ),
  );
  return <div class="message-prose" innerHTML={html()} />;
}
