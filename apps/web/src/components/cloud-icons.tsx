"use client";

import { type SVGProps } from "react";

interface CloudIconProps extends SVGProps<SVGSVGElement> {
  size?: number;
}

// AWS EC2 - Server instance
export function IconEC2({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <rect x="4" y="8" width="32" height="24" rx="3" fill="#FF9900" fillOpacity="0.15" stroke="#FF9900" strokeWidth="1.5" />
      <rect x="10" y="13" width="8" height="6" rx="1" fill="#FF9900" fillOpacity="0.4" />
      <rect x="22" y="13" width="8" height="6" rx="1" fill="#FF9900" fillOpacity="0.4" />
      <rect x="10" y="23" width="8" height="4" rx="1" fill="#FF9900" fillOpacity="0.3" />
      <rect x="22" y="23" width="8" height="4" rx="1" fill="#FF9900" fillOpacity="0.3" />
      <circle cx="12" cy="16" r="1" fill="#FF9900" />
      <circle cx="24" cy="16" r="1" fill="#FF9900" />
    </svg>
  );
}

// AWS RDS - Database
export function IconRDS({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <ellipse cx="20" cy="12" rx="14" ry="5" fill="#3B48CC" fillOpacity="0.15" stroke="#527FFF" strokeWidth="1.5" />
      <path d="M6 12v8c0 2.76 6.27 5 14 5s14-2.24 14-5v-8" stroke="#527FFF" strokeWidth="1.5" fill="#3B48CC" fillOpacity="0.08" />
      <path d="M6 20v8c0 2.76 6.27 5 14 5s14-2.24 14-5v-8" stroke="#527FFF" strokeWidth="1.5" fill="#3B48CC" fillOpacity="0.08" />
      <ellipse cx="20" cy="20" rx="14" ry="5" fill="none" stroke="#527FFF" strokeWidth="0.5" strokeOpacity="0.4" />
    </svg>
  );
}

// AWS ElastiCache - Cache
export function IconElastiCache({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <rect x="6" y="6" width="28" height="28" rx="4" fill="#C925D1" fillOpacity="0.12" stroke="#C925D1" strokeWidth="1.5" />
      <path d="M14 14h12M14 20h12M14 26h8" stroke="#C925D1" strokeWidth="2" strokeLinecap="round" />
      <circle cx="29" cy="14" r="2" fill="#C925D1" fillOpacity="0.5" />
      <circle cx="29" cy="20" r="2" fill="#C925D1" fillOpacity="0.5" />
      <path d="M20 10l2-3M24 10l2-3M16 10l2-3" stroke="#C925D1" strokeWidth="1" strokeLinecap="round" strokeOpacity="0.5" />
    </svg>
  );
}

// AWS ELB/ALB - Load Balancer
export function IconALB({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <circle cx="20" cy="20" r="15" fill="#8C4FFF" fillOpacity="0.1" stroke="#8C4FFF" strokeWidth="1.5" />
      <circle cx="20" cy="12" r="3" fill="#8C4FFF" fillOpacity="0.4" stroke="#8C4FFF" strokeWidth="1" />
      <circle cx="12" cy="26" r="3" fill="#8C4FFF" fillOpacity="0.4" stroke="#8C4FFF" strokeWidth="1" />
      <circle cx="28" cy="26" r="3" fill="#8C4FFF" fillOpacity="0.4" stroke="#8C4FFF" strokeWidth="1" />
      <line x1="20" y1="15" x2="14" y2="24" stroke="#8C4FFF" strokeWidth="1.5" />
      <line x1="20" y1="15" x2="26" y2="24" stroke="#8C4FFF" strokeWidth="1.5" />
      <line x1="14" y1="26" x2="26" y2="26" stroke="#8C4FFF" strokeWidth="1" strokeOpacity="0.4" strokeDasharray="2 2" />
    </svg>
  );
}

// AWS S3 - Storage
export function IconS3({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <path d="M8 10l12-4 12 4v20l-12 4-12-4V10z" fill="#3ECF8E" fillOpacity="0.1" stroke="#3ECF8E" strokeWidth="1.5" />
      <path d="M8 10l12 4 12-4" stroke="#3ECF8E" strokeWidth="1.5" />
      <path d="M20 14v20" stroke="#3ECF8E" strokeWidth="1" strokeOpacity="0.4" />
      <path d="M8 18l12 4 12-4" stroke="#3ECF8E" strokeWidth="0.8" strokeOpacity="0.3" />
      <path d="M8 26l12 4 12-4" stroke="#3ECF8E" strokeWidth="0.8" strokeOpacity="0.3" />
    </svg>
  );
}

// AWS Lambda - Serverless Function
export function IconLambda({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <rect x="5" y="5" width="30" height="30" rx="4" fill="#FF9900" fillOpacity="0.1" stroke="#FF9900" strokeWidth="1.5" />
      <path d="M12 30l8-20 4 10 6-12" stroke="#FF9900" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// AWS SQS - Message Queue
export function IconSQS({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <rect x="4" y="10" width="32" height="20" rx="3" fill="#FF4F8B" fillOpacity="0.12" stroke="#FF4F8B" strokeWidth="1.5" />
      <rect x="8" y="15" width="6" height="10" rx="1.5" fill="#FF4F8B" fillOpacity="0.3" />
      <rect x="17" y="15" width="6" height="10" rx="1.5" fill="#FF4F8B" fillOpacity="0.3" />
      <rect x="26" y="15" width="6" height="10" rx="1.5" fill="#FF4F8B" fillOpacity="0.3" />
      <path d="M14 20h3M23 20h3" stroke="#FF4F8B" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

// AWS CloudFront - CDN
export function IconCloudFront({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <circle cx="20" cy="20" r="14" fill="#8C4FFF" fillOpacity="0.08" stroke="#8C4FFF" strokeWidth="1.5" />
      <ellipse cx="20" cy="20" rx="14" ry="6" stroke="#8C4FFF" strokeWidth="1" strokeOpacity="0.4" />
      <ellipse cx="20" cy="20" rx="6" ry="14" stroke="#8C4FFF" strokeWidth="1" strokeOpacity="0.4" />
      <circle cx="20" cy="20" r="3" fill="#8C4FFF" fillOpacity="0.5" />
      <line x1="20" y1="6" x2="20" y2="34" stroke="#8C4FFF" strokeWidth="0.5" strokeOpacity="0.3" />
      <line x1="6" y1="20" x2="34" y2="20" stroke="#8C4FFF" strokeWidth="0.5" strokeOpacity="0.3" />
    </svg>
  );
}

// Generic Database
export function IconDatabase({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <ellipse cx="20" cy="11" rx="13" ry="5" fill="#f97316" fillOpacity="0.15" stroke="#f97316" strokeWidth="1.5" />
      <path d="M7 11v8c0 2.76 5.82 5 13 5s13-2.24 13-5v-8" stroke="#f97316" strokeWidth="1.5" fill="#f97316" fillOpacity="0.06" />
      <path d="M7 19v8c0 2.76 5.82 5 13 5s13-2.24 13-5v-8" stroke="#f97316" strokeWidth="1.5" fill="#f97316" fillOpacity="0.06" />
    </svg>
  );
}

// Generic Server
export function IconServer({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <rect x="6" y="5" width="28" height="12" rx="3" fill="#22c55e" fillOpacity="0.1" stroke="#22c55e" strokeWidth="1.5" />
      <rect x="6" y="23" width="28" height="12" rx="3" fill="#22c55e" fillOpacity="0.1" stroke="#22c55e" strokeWidth="1.5" />
      <circle cx="12" cy="11" r="1.5" fill="#22c55e" />
      <circle cx="12" cy="29" r="1.5" fill="#22c55e" />
      <line x1="17" y1="11" x2="28" y2="11" stroke="#22c55e" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.4" />
      <line x1="17" y1="29" x2="28" y2="29" stroke="#22c55e" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.4" />
    </svg>
  );
}

// Generic Cache
export function IconCache({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <rect x="6" y="6" width="28" height="28" rx="14" fill="#ef4444" fillOpacity="0.1" stroke="#ef4444" strokeWidth="1.5" />
      <path d="M15 16h10M15 20h10M15 24h6" stroke="#ef4444" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M20 8l1.5-2M24 9l1.5-2M16 9l1.5-2" stroke="#ef4444" strokeWidth="1" strokeLinecap="round" strokeOpacity="0.5" />
    </svg>
  );
}

// Generic Load Balancer
export function IconLoadBalancer({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <circle cx="20" cy="20" r="15" fill="#3b82f6" fillOpacity="0.1" stroke="#3b82f6" strokeWidth="1.5" />
      <circle cx="20" cy="11" r="3" fill="#3b82f6" fillOpacity="0.4" stroke="#3b82f6" strokeWidth="1" />
      <circle cx="12" cy="27" r="3" fill="#3b82f6" fillOpacity="0.4" stroke="#3b82f6" strokeWidth="1" />
      <circle cx="28" cy="27" r="3" fill="#3b82f6" fillOpacity="0.4" stroke="#3b82f6" strokeWidth="1" />
      <line x1="20" y1="14" x2="14" y2="25" stroke="#3b82f6" strokeWidth="1.5" />
      <line x1="20" y1="14" x2="26" y2="25" stroke="#3b82f6" strokeWidth="1.5" />
    </svg>
  );
}

// Generic Queue
export function IconQueue({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <rect x="4" y="10" width="32" height="20" rx="3" fill="#a855f7" fillOpacity="0.12" stroke="#a855f7" strokeWidth="1.5" />
      <rect x="8" y="15" width="6" height="10" rx="1.5" fill="#a855f7" fillOpacity="0.3" />
      <rect x="17" y="15" width="6" height="10" rx="1.5" fill="#a855f7" fillOpacity="0.3" />
      <rect x="26" y="15" width="6" height="10" rx="1.5" fill="#a855f7" fillOpacity="0.3" />
      <path d="M14 20h3M23 20h3" stroke="#a855f7" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

// Generic DNS
export function IconDNS({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <circle cx="20" cy="20" r="14" fill="#06b6d4" fillOpacity="0.1" stroke="#06b6d4" strokeWidth="1.5" />
      <ellipse cx="20" cy="20" rx="14" ry="6" stroke="#06b6d4" strokeWidth="1" strokeOpacity="0.4" />
      <ellipse cx="20" cy="20" rx="6" ry="14" stroke="#06b6d4" strokeWidth="1" strokeOpacity="0.4" />
      <line x1="6" y1="20" x2="34" y2="20" stroke="#06b6d4" strokeWidth="0.5" strokeOpacity="0.3" />
      <line x1="20" y1="6" x2="20" y2="34" stroke="#06b6d4" strokeWidth="0.5" strokeOpacity="0.3" />
    </svg>
  );
}

// Generic Storage
export function IconStorage({ size = 40, ...props }: CloudIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <path d="M8 10l12-4 12 4v20l-12 4-12-4V10z" fill="#64748b" fillOpacity="0.1" stroke="#64748b" strokeWidth="1.5" />
      <path d="M8 10l12 4 12-4" stroke="#64748b" strokeWidth="1.5" />
      <path d="M20 14v20" stroke="#64748b" strokeWidth="1" strokeOpacity="0.4" />
    </svg>
  );
}

// Map of service type to icon component
export type CloudServiceType =
  | "cloudfront"
  | "alb"
  | "ec2"
  | "rds"
  | "elasticache"
  | "lambda"
  | "sqs"
  | "s3"
  | "database"
  | "app_server"
  | "cache"
  | "load_balancer"
  | "queue"
  | "dns"
  | "storage"
  | "custom";

export function CloudIcon({ type, size = 40, ...props }: { type: string; size?: number } & SVGProps<SVGSVGElement>) {
  switch (type) {
    case "cloudfront": return <IconCloudFront size={size} {...props} />;
    case "alb": return <IconALB size={size} {...props} />;
    case "ec2": return <IconEC2 size={size} {...props} />;
    case "rds": return <IconRDS size={size} {...props} />;
    case "elasticache": return <IconElastiCache size={size} {...props} />;
    case "lambda": return <IconLambda size={size} {...props} />;
    case "sqs": return <IconSQS size={size} {...props} />;
    case "s3": return <IconS3 size={size} {...props} />;
    case "database": return <IconDatabase size={size} {...props} />;
    case "app_server": return <IconServer size={size} {...props} />;
    case "cache": return <IconCache size={size} {...props} />;
    case "load_balancer": return <IconLoadBalancer size={size} {...props} />;
    case "queue": return <IconQueue size={size} {...props} />;
    case "dns": return <IconDNS size={size} {...props} />;
    case "storage": return <IconStorage size={size} {...props} />;
    default: return <IconServer size={size} {...props} />;
  }
}

// Brand colors for cloud service types
export const SERVICE_COLORS: Record<string, { primary: string; bg: string; label: string }> = {
  cloudfront: { primary: "#8C4FFF", bg: "#8C4FFF15", label: "CloudFront" },
  alb: { primary: "#8C4FFF", bg: "#8C4FFF15", label: "ALB" },
  ec2: { primary: "#FF9900", bg: "#FF990015", label: "EC2" },
  rds: { primary: "#527FFF", bg: "#527FFF15", label: "RDS" },
  elasticache: { primary: "#C925D1", bg: "#C925D115", label: "ElastiCache" },
  lambda: { primary: "#FF9900", bg: "#FF990015", label: "Lambda" },
  sqs: { primary: "#FF4F8B", bg: "#FF4F8B15", label: "SQS" },
  s3: { primary: "#3ECF8E", bg: "#3ECF8E15", label: "S3" },
  database: { primary: "#f97316", bg: "#f9731615", label: "Database" },
  app_server: { primary: "#22c55e", bg: "#22c55e15", label: "Server" },
  cache: { primary: "#ef4444", bg: "#ef444415", label: "Cache" },
  load_balancer: { primary: "#3b82f6", bg: "#3b82f615", label: "LB" },
  queue: { primary: "#a855f7", bg: "#a855f715", label: "Queue" },
  dns: { primary: "#06b6d4", bg: "#06b6d415", label: "DNS" },
  storage: { primary: "#64748b", bg: "#64748b15", label: "Storage" },
  custom: { primary: "#94a3b8", bg: "#94a3b815", label: "Service" },
};

export function getServiceColor(type: string) {
  return SERVICE_COLORS[type] || SERVICE_COLORS.custom;
}
