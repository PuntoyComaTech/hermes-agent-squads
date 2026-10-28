const CODE_FILE = "page.tsx";
const GET_STARTED = "To get started, edit the ";
const LEARNING_LABEL = "Learning";
const LINE_END = " file.";
const LINE_START = "Looking for a starting point or more instructions? Head over to ";
const LINK_CLASS = "font-medium text-zinc-950 dark:text-zinc-50";
const MIDDLE = " or the ";
const TAIL = " center.";
const TEMPLATE_LABEL = "Templates";

export function DocsIntro(): React.JSX.Element {
  return (
    <div className="flex flex-col items-center gap-6 text-center sm:items-start sm:text-left">
      <h1 className="max-w-xs text-3xl font-semibold leading-10 tracking-tight text-black dark:text-zinc-50">
        {GET_STARTED}
        <code className="rounded bg-black/[.06] px-1.5 py-0.5 font-mono text-[0.9em] dark:bg-white/[.08]">
          {CODE_FILE}
        </code>
        {LINE_END}
      </h1>
      <p className="max-w-md text-lg leading-8 text-zinc-600 dark:text-zinc-400">
        {LINE_START}
        <a
          className={LINK_CLASS}
          href="https://vercel.com/templates?framework=next.js&utm_source=create-next-app&utm_medium=appdir-template-tw&utm_campaign=create-next-app"
        >
          {TEMPLATE_LABEL}
        </a>
        {MIDDLE}
        <a
          className={LINK_CLASS}
          href="https://nextjs.org/learn?utm_source=create-next-app&utm_medium=appdir-template-tw&utm_campaign=create-next-app"
        >
          {LEARNING_LABEL}
        </a>
        {TAIL}
      </p>
    </div>
  );
}
