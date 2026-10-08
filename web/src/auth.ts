import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import { isAllowedByEnv } from "@/lib/auth/allowed";

const SEVEN_DAYS = 60 * 60 * 24 * 7;

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    }),
  ],
  session: { strategy: "jwt", maxAge: SEVEN_DAYS },
  pages: { signIn: "/login", error: "/acesso-negado" },
  callbacks: {
    // Só entra e-mail verificado pelo Google e presente em ALLOWED_EMAILS.
    signIn({ profile }) {
      return profile?.email_verified === true && isAllowedByEnv(profile.email);
    },
  },
});
