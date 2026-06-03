import { AlertTriangle, Database, FileText } from "lucide-react";
import type { QueryResponse } from "../types/api";

interface ResponseRendererProps {
  response: QueryResponse;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
}

function TableRenderer({ response }: ResponseRendererProps) {
  const rows = response.data ?? [];
  const headers = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));

  return (
    <div className="response-block">
      <div className="response-label">
        <Database size={15} />
        <span>Dữ liệu</span>
      </div>
      {response.answer ? <p className="answer-text">{response.answer}</p> : null}
      {rows.length > 0 && headers.length > 0 ? (
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                {headers.map((header) => (
                  <th key={header}>{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {headers.map((header) => (
                    <td key={header}>{formatValue(row[header])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

function WarningRenderer({ response }: ResponseRendererProps) {
  return (
    <div className="response-block warning-response">
      <div className="response-label">
        <AlertTriangle size={15} />
        <span>Cảnh báo y tế</span>
      </div>
      <p className="answer-text">{response.answer}</p>
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
      <p className="answer-text">{response.answer}</p>
    </div>
  );
}

export function ResponseRenderer({ response }: ResponseRendererProps) {
  if (response.response_type === "table") {
    return <TableRenderer response={response} />;
  }

  if (response.response_type === "warning") {
    return <WarningRenderer response={response} />;
  }

  return <TextRenderer response={response} />;
}
