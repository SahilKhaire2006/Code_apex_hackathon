import type { Metadata } from "next";
import { Inter, Noto_Sans, Source_Code_Pro } from "next/font/google";
import "@/styles/globals.css";
import { ThemeProvider } from "@/components/ui/ThemeProvider";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const notoSans = Noto_Sans({ subsets: ["latin", "devanagari"], variable: "--font-noto-sans" });
const sourceCodePro = Source_Code_Pro({ subsets: ["latin"], variable: "--font-source-code-pro" });

export const metadata: Metadata = {
  title: "PolicyGuard AI",
  description: "Agentic compliance dashboard for policy and transaction validation",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html suppressHydrationWarning lang="en" className={`${inter.variable} ${notoSans.variable} ${sourceCodePro.variable}`}>
      <body>
        <div className="gov-top-stripe" aria-hidden />
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
