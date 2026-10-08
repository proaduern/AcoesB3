import Link from "next/link";
import type { ReactNode } from "react";
import { signOut } from "@/auth";
import { DataFooter } from "@/components/DataFooter";
import { requireUser } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const user = await requireUser();
  return (
    <>
      <header className="topbar">
        <nav aria-label="Principal">
          <Link href="/">Lista</Link>
          <Link href="/filtro">Filtro</Link>
          <Link href="/backtest">Backtest</Link>
        </nav>
        <form
          action={async () => {
            "use server";
            await signOut({ redirectTo: "/login" });
          }}
        >
          <span className="who">{user.email}</span>
          <button type="submit">Sair</button>
        </form>
      </header>
      {children}
      <DataFooter />
    </>
  );
}
