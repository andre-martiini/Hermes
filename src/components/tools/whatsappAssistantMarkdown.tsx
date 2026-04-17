import React from 'react';
import { isInternalAppHref, navigateWithinApp } from '../../utils/internalNavigation';

type MarkdownBlock =
  | { type: 'paragraph'; text: string }
  | { type: 'heading'; text: string; level: 1 | 2 | 3 }
  | { type: 'blockquote'; text: string }
  | { type: 'code'; code: string; language?: string }
  | { type: 'unordered-list'; items: string[] }
  | { type: 'ordered-list'; items: string[] }
  | { type: 'spacer' };

const INLINE_PATTERN =
  /\[([^\]]+)\]\(([^)\s]+)\)|`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*/g;
const URL_PATTERN = /(https?:\/\/[^\s]+)/g;

const renderLinkNode = (
  href: string,
  key: string,
  children: React.ReactNode,
): React.ReactNode => {
  if (isInternalAppHref(href)) {
    return (
      <a
        key={key}
        href={href}
        onClick={(event) => {
          event.preventDefault();
          navigateWithinApp(href);
        }}
        className="font-semibold text-blue-700 underline decoration-blue-200 underline-offset-2 hover:text-blue-900"
      >
        {children}
      </a>
    );
  }

  return (
    <a
      key={key}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-semibold text-blue-700 underline decoration-blue-200 underline-offset-2 hover:text-blue-900"
    >
      {children}
    </a>
  );
};

const pushTextWithAutoLinks = (
  value: string,
  keyPrefix: string,
  nodes: React.ReactNode[],
): void => {
  if (!value) {
    return;
  }

  const parts = value.split(URL_PATTERN);
  parts.forEach((part, index) => {
    if (!part) {
      return;
    }

    if (/^https?:\/\//.test(part)) {
      nodes.push(renderLinkNode(part, `${keyPrefix}_url_${index}`, part));
      return;
    }

    nodes.push(<React.Fragment key={`${keyPrefix}_txt_${index}`}>{part}</React.Fragment>);
  });
};

const renderInlineMarkdown = (text: string, keyPrefix: string): React.ReactNode[] => {
  const nodes: React.ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;

  INLINE_PATTERN.lastIndex = 0;
  while ((match = INLINE_PATTERN.exec(text)) !== null) {
    if (match.index > cursor) {
      pushTextWithAutoLinks(text.slice(cursor, match.index), `${keyPrefix}_${cursor}`, nodes);
    }

    if (match[1] && match[2]) {
      nodes.push(renderLinkNode(match[2], `${keyPrefix}_${match.index}`, match[1]));
    } else if (match[3]) {
      nodes.push(
        <code
          key={`${keyPrefix}_${match.index}`}
          className="rounded-md border border-slate-200 bg-slate-100 px-1.5 py-0.5 font-mono text-[0.85em] text-slate-700"
        >
          {match[3]}
        </code>,
      );
    } else if (match[4]) {
      nodes.push(
        <strong key={`${keyPrefix}_${match.index}`} className="font-extrabold text-slate-900">
          {match[4]}
        </strong>,
      );
    } else if (match[5]) {
      nodes.push(
        <em key={`${keyPrefix}_${match.index}`} className="italic text-slate-700">
          {match[5]}
        </em>,
      );
    }

    cursor = INLINE_PATTERN.lastIndex;
  }

  if (cursor < text.length) {
    pushTextWithAutoLinks(text.slice(cursor), `${keyPrefix}_tail`, nodes);
  }

  return nodes;
};

const parseMarkdownBlocks = (markdown: string): MarkdownBlock[] => {
  const blocks: MarkdownBlock[] = [];
  const lines = markdown.replace(/\r\n/g, '\n').split('\n');
  let paragraphBuffer: string[] = [];
  let listBuffer: string[] = [];
  let listType: 'unordered-list' | 'ordered-list' | null = null;
  let inCodeBlock = false;
  let codeLanguage = '';
  let codeLines: string[] = [];

  const flushParagraph = () => {
    if (!paragraphBuffer.length) {
      return;
    }
    blocks.push({ type: 'paragraph', text: paragraphBuffer.join(' ') });
    paragraphBuffer = [];
  };

  const flushList = () => {
    if (!listType || !listBuffer.length) {
      return;
    }
    blocks.push({ type: listType, items: [...listBuffer] });
    listType = null;
    listBuffer = [];
  };

  const flushCode = () => {
    if (!codeLines.length && !codeLanguage) {
      return;
    }
    blocks.push({ type: 'code', code: codeLines.join('\n'), language: codeLanguage || undefined });
    codeLines = [];
    codeLanguage = '';
  };

  lines.forEach((line) => {
    const trimmed = line.trim();

    if (trimmed.startsWith('```')) {
      flushParagraph();
      flushList();
      if (inCodeBlock) {
        flushCode();
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
        codeLanguage = trimmed.slice(3).trim();
      }
      return;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      return;
    }

    if (!trimmed) {
      flushParagraph();
      flushList();
      blocks.push({ type: 'spacer' });
      return;
    }

    const headingMatch = trimmed.match(/^(#{1,3})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      blocks.push({
        type: 'heading',
        level: headingMatch[1].length as 1 | 2 | 3,
        text: headingMatch[2],
      });
      return;
    }

    if (trimmed.startsWith('>')) {
      flushParagraph();
      flushList();
      blocks.push({ type: 'blockquote', text: trimmed.replace(/^>\s?/, '') });
      return;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      flushParagraph();
      if (listType && listType !== 'unordered-list') {
        flushList();
      }
      listType = 'unordered-list';
      listBuffer.push(trimmed.replace(/^[-*]\s+/, ''));
      return;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      flushParagraph();
      if (listType && listType !== 'ordered-list') {
        flushList();
      }
      listType = 'ordered-list';
      listBuffer.push(trimmed.replace(/^\d+\.\s+/, ''));
      return;
    }

    flushList();
    paragraphBuffer.push(trimmed);
  });

  if (inCodeBlock) {
    flushCode();
  }
  flushParagraph();
  flushList();

  return blocks;
};

export const WhatsAppAssistantMarkdown: React.FC<{ markdown: string }> = ({ markdown }) => {
  const blocks = parseMarkdownBlocks(markdown);

  return (
    <div className="space-y-3 text-sm leading-7 text-slate-700">
      {blocks.map((block, index) => {
        if (block.type === 'spacer') {
          return <div key={`spacer_${index}`} className="h-1" />;
        }

        if (block.type === 'heading') {
          const className =
            block.level === 1
              ? 'text-base font-black tracking-tight text-slate-900'
              : block.level === 2
                ? 'text-[15px] font-black tracking-tight text-slate-900'
                : 'text-sm font-black uppercase tracking-[0.18em] text-slate-500';
          return (
            <div key={`heading_${index}`} className={className}>
              {renderInlineMarkdown(block.text, `heading_${index}`)}
            </div>
          );
        }

        if (block.type === 'paragraph') {
          return (
            <p key={`paragraph_${index}`} className="whitespace-pre-wrap break-words">
              {renderInlineMarkdown(block.text, `paragraph_${index}`)}
            </p>
          );
        }

        if (block.type === 'blockquote') {
          return (
            <blockquote
              key={`quote_${index}`}
              className="rounded-r-2xl border-l-4 border-slate-300 bg-slate-50 px-4 py-3 text-slate-600"
            >
              {renderInlineMarkdown(block.text, `quote_${index}`)}
            </blockquote>
          );
        }

        if (block.type === 'code') {
          return (
            <div key={`code_${index}`} className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-950">
              {block.language && (
                <div className="border-b border-slate-800 px-4 py-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
                  {block.language}
                </div>
              )}
              <pre className="overflow-x-auto px-4 py-4 text-xs leading-6 text-slate-100">
                <code>{block.code}</code>
              </pre>
            </div>
          );
        }

        if (block.type === 'unordered-list') {
          return (
            <ul key={`ul_${index}`} className="space-y-2 pl-5">
              {block.items.map((item, itemIndex) => (
                <li key={`ul_${index}_${itemIndex}`} className="list-disc break-words">
                  {renderInlineMarkdown(item, `ul_${index}_${itemIndex}`)}
                </li>
              ))}
            </ul>
          );
        }

        return (
          <ol key={`ol_${index}`} className="space-y-2 pl-5">
            {block.items.map((item, itemIndex) => (
              <li key={`ol_${index}_${itemIndex}`} className="list-decimal break-words">
                {renderInlineMarkdown(item, `ol_${index}_${itemIndex}`)}
              </li>
            ))}
          </ol>
        );
      })}
    </div>
  );
};
