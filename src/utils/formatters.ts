/**
 * Unified value formatting utilities for the NLQ dashboard
 *
 * This module consolidates all number/value formatting logic that was previously
 * duplicated across multiple components (KPITile, ChartTile, useDashboardData, etc.)
 */

export type FormatType = 'currency' | 'percent' | 'months' | 'number';

export interface FormatOptions {
  /** Format type: currency, percent, months, or number */
  format?: FormatType;
  /** Unit hint from data (e.g., '%', '$', '$M', 'USD_MILLIONS') */
  unit?: string;
  /** Optional suffix to append */
  suffix?: string;
  /** Number of decimal places (default varies by format) */
  decimals?: number;
  /** Whether to show currency symbol for currency format (default true) */
  showCurrencySymbol?: boolean;
}

/**
 * Format a numeric value for display with intelligent abbreviation
 *
 * @param value - The number or string to format
 * @param options - Formatting options
 * @returns Formatted string
 *
 * @example
 * formatValue(1234567, { format: 'currency' }) // "$1.2M"
 * formatValue(45.5, { format: 'percent' }) // "45.5%"
 * formatValue(3, { format: 'months' }) // "3 months"
 * formatValue(1500, { format: 'number' }) // "1.5K"
 */
export function formatValue(
  value: number | string | null | undefined,
  options: FormatOptions = {}
): string {
  // Handle null/undefined
  if (value === null || value === undefined) {
    return '-';
  }

  // Handle string pass-through
  if (typeof value === 'string') {
    return options.suffix ? `${value}${options.suffix}` : value;
  }

  const { format, unit, suffix, decimals } = options;

  // Determine format from unit if format not specified
  const effectiveFormat = format ?? inferFormatFromUnit(unit);

  let formattedValue: string;

  switch (effectiveFormat) {
    case 'currency':
      formattedValue = formatCurrency(value, decimals);
      break;

    case 'percent':
      formattedValue = formatPercent(value, decimals);
      break;

    case 'months':
      formattedValue = formatMonths(value);
      break;

    case 'number':
    default:
      formattedValue = formatNumber(value, decimals);
      break;
  }

  return suffix ? `${formattedValue}${suffix}` : formattedValue;
}

/**
 * Format a value as currency with intelligent abbreviation
 *
 * @example
 * formatCurrency(1234567890) // "$1.2B"
 * formatCurrency(1234567) // "$1.2M"
 * formatCurrency(1234) // "$1K"
 * formatCurrency(123) // "$123"
 */
export function formatCurrency(value: number, decimals?: number): string {
  const absValue = Math.abs(value);

  if (absValue >= 1_000_000_000) {
    return `$${(value / 1_000_000_000).toFixed(decimals ?? 1)}B`;
  } else if (absValue >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(decimals ?? 1)}M`;
  } else if (absValue >= 1_000) {
    return `$${(value / 1_000).toFixed(decimals ?? 0)}K`;
  }
  return `$${value.toFixed(decimals ?? 0)}`;
}

/**
 * Format a value as a percentage
 *
 * @example
 * formatPercent(45.567) // "45.6%"
 * formatPercent(100) // "100.0%"
 */
export function formatPercent(value: number, decimals: number = 1): string {
  return `${value.toFixed(decimals)}%`;
}

/**
 * Format a value as months (with proper pluralization)
 *
 * @example
 * formatMonths(1) // "1 month"
 * formatMonths(3.5) // "4 months"
 */
export function formatMonths(value: number): string {
  const rounded = Math.round(value);
  return `${rounded} month${rounded !== 1 ? 's' : ''}`;
}

/**
 * Format a plain number with intelligent abbreviation (no currency symbol)
 *
 * @example
 * formatNumber(1234567890) // "1.2B"
 * formatNumber(1234567) // "1.2M"
 * formatNumber(1234) // "1.2K"
 * formatNumber(123) // "123"
 */
export function formatNumber(value: number, decimals?: number): string {
  const absValue = Math.abs(value);

  if (absValue >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(decimals ?? 1)}B`;
  } else if (absValue >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(decimals ?? 1)}M`;
  } else if (absValue >= 1_000) {
    return `${(value / 1_000).toFixed(decimals ?? 1)}K`;
  }
  return value.toLocaleString();
}

/**
 * Infer format type from a unit string
 */
function inferFormatFromUnit(unit?: string): FormatType {
  if (!unit) return 'number';

  const normalizedUnit = unit.toLowerCase().trim();

  if (normalizedUnit === '%' || normalizedUnit === 'percent') {
    return 'percent';
  }

  if (
    normalizedUnit === '$' ||
    normalizedUnit === '$m' ||
    normalizedUnit === 'usd' ||
    normalizedUnit === 'usd_millions' ||
    normalizedUnit === 'currency'
  ) {
    return 'currency';
  }

  if (normalizedUnit === 'months' || normalizedUnit === 'month') {
    return 'months';
  }

  return 'number';
}

/**
 * Format a chart axis tick value (shorter format for axis labels)
 *
 * @example
 * formatAxisValue(1234567) // "1.2M"
 */
export function formatAxisValue(value: number): string {
  return formatNumber(value);
}

/**
 * Format a tooltip value (more detailed format)
 *
 * @example
 * formatTooltipValue(1234567.89, 'currency') // "$1,234,567.89"
 */
export function formatTooltipValue(value: number, format?: FormatType): string {
  switch (format) {
    case 'currency':
      return `$${value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
    case 'percent':
      return `${value.toFixed(1)}%`;
    default:
      return value.toLocaleString();
  }
}
