import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

// Main utility function for combining classes
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
