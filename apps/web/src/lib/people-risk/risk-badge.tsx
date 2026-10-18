/**
 * People Risk 共通 riskBadge ヘルパー
 *
 * members/page.tsx と members/[id]/page.tsx で重複していた
 * riskBadge 関数を1箇所にまとめたものです。
 */

import { Badge } from "@/components/ui/badge";

/**
 * リスクレベルに応じた Badge を返します。
 *
 * @param level - "critical" | "warning" | その他（safe）
 */
export function riskBadge(level: string | null) {
  switch (level) {
    case "critical":
      return <Badge variant="red">危険</Badge>;
    case "warning":
      return <Badge variant="yellow">注意</Badge>;
    default:
      return <Badge variant="green">安全</Badge>;
  }
}
