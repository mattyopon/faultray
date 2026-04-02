import { getDictionary } from "@/i18n/get-dictionary";
import type { Metadata } from "next";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary("ja");
  return {
    title: dict.metadata.title,
    description: dict.metadata.description,
  };
}

export default function JaLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
