import { createFileRoute } from "@tanstack/react-router";

const CODE_PATH = "src/routes/index.tsx";
const BEFORE_CODE = "Edit ";
const AFTER_CODE = " to get started.";
const TITLE = "Welcome to TanStack Start";

function Home(): React.JSX.Element {
  return (
    <div className="p-8">
      <h1 className="text-4xl font-bold">{TITLE}</h1>
      <p className="mt-4 text-lg">
        {BEFORE_CODE}
        <code>{CODE_PATH}</code>
        {AFTER_CODE}
      </p>
    </div>
  );
}

export const Route = createFileRoute("/")({ component: Home });
