import Image from "next/image";

const DEPLOY_LABEL = "Deploy Now";
const DOC_LABEL = "Documentation";
const VERCEL_HEIGHT = 14;
const VERCEL_WIDTH = 16;

export function ActionLinks(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-4 text-base font-medium sm:flex-row">
      <a
        className="flex h-12 w-full items-center justify-center gap-2 rounded-full bg-foreground px-5 text-background transition-colors hover:bg-[#383838] dark:hover:bg-[#ccc] md:w-[158px]"
        href="https://vercel.com/new?utm_source=create-next-app&utm_medium=appdir-template-tw&utm_campaign=create-next-app"
        rel="noopener noreferrer"
        target="_blank"
      >
        <Image
          alt="Vercel logomark"
          className="dark:invert h-[14px] w-4"
          height={VERCEL_HEIGHT}
          src="/vercel.svg"
          width={VERCEL_WIDTH}
        />
        {DEPLOY_LABEL}
      </a>
      <a
        className="flex h-12 w-full items-center justify-center rounded-full border border-solid border-black/[.08] px-5 transition-colors hover:border-transparent hover:bg-black/[.04] dark:border-white/[.145] dark:hover:bg-[#1a1a1a] md:w-[158px]"
        href="https://nextjs.org/docs?utm_source=create-next-app&utm_medium=appdir-template-tw&utm_campaign=create-next-app"
        rel="noopener noreferrer"
        target="_blank"
      >
        {DOC_LABEL}
      </a>
    </div>
  );
}
