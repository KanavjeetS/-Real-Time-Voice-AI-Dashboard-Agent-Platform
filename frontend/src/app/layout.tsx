import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Calling Agent",
  description: "Real-time AI voice calling agent dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-gray-950 text-gray-100 min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
