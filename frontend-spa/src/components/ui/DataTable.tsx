import type { ReactNode } from "react";

export function DataTable({
  columns,
  rows,
  renderCell,
}: {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  renderCell?: (row: Record<string, unknown>, column: string) => ReactNode;
}): JSX.Element {
  return (
    <div className="ui-data-table-wrap">
      <table className="ui-data-table">
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column) => (
                <td key={column}>{renderCell ? renderCell(row, column) : String(row[column] ?? "")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
