import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// react-markdown does not render raw HTML by default (HTML comments such as the PR-comment marker are dropped), so report text cannot inject markup.
export default function Markdown({ text }: { text: string }) {
  return <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown></div>
}
