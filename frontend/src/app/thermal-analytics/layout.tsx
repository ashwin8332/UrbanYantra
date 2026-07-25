import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Thermal Analytics — UrbanYantra",
  description:
    "Upload satellite imagery to detect urban heat islands and receive AI-powered mitigation strategies.",
};

export default function ThermalAnalyticsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="h-full overflow-y-auto">{children}</div>
  );
}
