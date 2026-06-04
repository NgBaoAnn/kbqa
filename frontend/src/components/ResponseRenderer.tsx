import { AlertTriangle, FileText } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { QueryResponse } from "../types/api";

interface ResponseRendererProps {
  response: QueryResponse;
}

function WarningRenderer({ response }: ResponseRendererProps) {
  return (
    <div className="response-block warning-response">
      <div className="response-label">
        <AlertTriangle size={15} />
        <span>Cảnh báo y tế</span>
      </div>
      <div className="markdown-prose">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{response.answer}</ReactMarkdown>
      </div>
    </div>
  );
}

function TextRenderer({ response }: ResponseRendererProps) {
  return (
    <div className="response-block">
      <div className="response-label">
        <FileText size={15} />
        <span>Trả lời</span>
      </div>
      <div className="markdown-prose">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{response.answer}</ReactMarkdown>
      </div>
    </div>
  );
}

export function ResponseRenderer({ response }: ResponseRendererProps) {
  // We no longer render a raw table. If response_type is "table", 
  // the data is already nicely formatted in Markdown by the backend.
  if (response.response_type === "warning") {
    return <WarningRenderer response={response} />;
  }

  return <TextRenderer response={response} />;
}
