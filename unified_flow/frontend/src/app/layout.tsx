import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Unified Flow | Zero-Edit Video Studio for Bharat",
  description:
    "Transform a single text prompt into a professional-grade, culturally resonant video in minutes. Built for Indian MSMEs.",
  keywords: [
    "AI video",
    "MSME",
    "India",
    "content creation",
    "AWS",
    "Bharat",
    "multilingual",
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} antialiased`}>{children}</body>
    </html>
  );
}
