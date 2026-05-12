export type StepperItem = {
  label: string;
  status?: "complete" | "active" | "pending" | "blocked";
};

export function Stepper({ items }: { items: StepperItem[] }): JSX.Element {
  return (
    <ol className="ui-stepper">
      {items.map((item) => (
        <li className={`ui-stepper__item is-${item.status || "pending"}`} key={item.label}>
          <span />
          {item.label}
        </li>
      ))}
    </ol>
  );
}
