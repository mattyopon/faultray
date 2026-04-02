import { getDictionary } from "@/i18n/get-dictionary";
import type { Metadata } from "next";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary("fr");
  return {
    title: dict.metadata.title,
    description: dict.metadata.description,
  };
}

export default function FrLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
