import Image from "next/image";
import { ActionLinks } from "../components/templates/action-links.tsx";
import { DocsIntro } from "../components/templates/docs-intro.tsx";

const LOGO_HEIGHT = 20;
const LOGO_WIDTH = 100;

export default function Home(): React.JSX.Element {
  return (
    <div className="flex flex-col flex-1 items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex flex-1 w-full max-w-3xl flex-col items-center justify-between py-32 px-16 bg-white dark:bg-black sm:items-start">
        <Image
          alt="Next.js logo"
          className="dark:invert h-5 w-[100px]"
          height={LOGO_HEIGHT}
          priority
          src="/next.svg"
          width={LOGO_WIDTH}
        />
        <DocsIntro />
        <ActionLinks />
      </main>
    </div>
  );
}
