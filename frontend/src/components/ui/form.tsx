import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";
import { Input } from "./input";

export function FormField({ label, hint, error, children, className }: { label: string; hint?: string; error?: string; children: ReactNode; className?: string }) {
  return <label className={cn("grid gap-1.5 text-sm font-medium", className)}><span>{label}</span>{children}{hint && !error && <span className="text-xs font-normal text-muted-foreground">{hint}</span>}{error && <span className="text-xs font-normal text-destructive" role="alert">{error}</span>}</label>;
}
export function FormInput(props: InputHTMLAttributes<HTMLInputElement>) { return <Input {...props} />; }
export function FormSelect({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) { return <select className={cn("h-10 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", className)} {...props} />; }
export function FormTextarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) { return <textarea className={cn("min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", className)} {...props} />; }
