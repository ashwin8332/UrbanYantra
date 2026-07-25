import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "UrbanYantra — Urban Heat Mitigation AI Platform",
  description:
    "Physics-informed AI intelligence platform for urban heat hotspot detection, SHAP driver attribution, and cooling scenario simulation.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} h-full`}>
      <body className="h-full overflow-hidden bg-[#0f1419] font-sans antialiased">{children}</body>
    </html>
  );
}
