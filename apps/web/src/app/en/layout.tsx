import { getDictionary } from "@/i18n/get-dictionary";
import type { Metadata } from "next";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary("en");
  return {
    title: dict.metadata.title,
    description: dict.metadata.description,
  };
}

export default function EnLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
