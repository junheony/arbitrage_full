import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Binance Futures Gap Monitor",
  description: "Real-time monitoring of Binance futures price gaps (시평갭)",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className="crt">
        {children}
      </body>
    </html>
  );
}
