import { FilePlus2 } from "lucide-react";
import { InlineErrorState } from "../StatusPrimitives";
import { Button, Field, Surface } from "../ui";

export function KnowledgeCreatePanel({
  content,
  disabled,
  error,
  isPending,
  onContentChange,
  onSave,
  onTitleChange,
  title,
}: {
  content: string;
  disabled: boolean;
  error?: Error | null;
  isPending: boolean;
  onContentChange: (value: string) => void;
  onSave: () => void;
  onTitleChange: (value: string) => void;
  title: string;
}): JSX.Element {
  return (
    <Surface
      className="ops-col-5"
      description="Capture a reviewed workspace note before it moves through the publish gate."
      eyebrow="Workspace Notes"
      title="Create Knowledge Record"
      tone="emphasis"
    >
      <div className="form-grid">
        <Field label="Title">
          <input value={title} onChange={(event) => onTitleChange(event.target.value)} />
        </Field>
        <Field label="Content" span>
          <textarea value={content} onChange={(event) => onContentChange(event.target.value)} rows={8} />
        </Field>
      </div>
      <div className="action-row">
        <Button
          disabled={disabled}
          icon={<FilePlus2 />}
          loading={isPending}
          onClick={onSave}
          variant="primary"
        >
          Save Knowledge
        </Button>
        <span className="muted">Knowledge records can be published into the team library after review.</span>
      </div>
      {error ? (
        <InlineErrorState title="Knowledge record was not saved" description={error.message} />
      ) : null}
    </Surface>
  );
}
