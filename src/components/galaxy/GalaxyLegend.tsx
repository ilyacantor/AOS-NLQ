import React from 'react';
import { DOMAIN_COLORS, FRESHNESS_COLORS } from './types';

interface GalaxyLegendProps {
  compact?: boolean;
}

export const GalaxyLegend: React.FC<GalaxyLegendProps> = ({ compact = false }) => {
  if (compact) {
    // Compact vertical layout for sidebar
    return (
      <div className="p-3 bg-slate-900/30 text-xs space-y-3">
        {/* Match Types */}
        <div>
          <span className="text-slate-500 text-[10px] uppercase tracking-wide">Match Type</span>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="text-slate-400">Exact</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-amber-500" />
              <span className="text-slate-400">Potential</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-slate-500" />
              <span className="text-slate-400">Hypothesis</span>
            </span>
          </div>
        </div>

        {/* Domains */}
        <div>
          <span className="text-slate-500 text-[10px] uppercase tracking-wide">Domain</span>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: DOMAIN_COLORS.finance }} />
              <span className="text-slate-400">Finance</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: DOMAIN_COLORS.growth }} />
              <span className="text-slate-400">Growth</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: DOMAIN_COLORS.ops }} />
              <span className="text-slate-400">Ops</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: DOMAIN_COLORS.product }} />
              <span className="text-slate-400">Product</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: DOMAIN_COLORS.people }} />
              <span className="text-slate-400">People</span>
            </span>
          </div>
        </div>
      </div>
    );
  }

  // Full horizontal layout (original)
  return (
    <div className="flex items-center justify-between px-4 py-3 bg-slate-900/50 border-t border-slate-800 text-xs">
      {/* Domain Colors */}
      <div className="flex items-center gap-4">
        <span className="text-slate-500 mr-2">Domains:</span>
        <span className="flex items-center gap-1.5">
          <span
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: DOMAIN_COLORS.finance }}
          />
          <span className="text-slate-400">Finance</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: DOMAIN_COLORS.growth }}
          />
          <span className="text-slate-400">Growth</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: DOMAIN_COLORS.ops }}
          />
          <span className="text-slate-400">Ops</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: DOMAIN_COLORS.product }}
          />
          <span className="text-slate-400">Product</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: DOMAIN_COLORS.people }}
          />
          <span className="text-slate-400">People</span>
        </span>
      </div>

      {/* Ring Legend */}
      <div className="flex items-center gap-4">
        <span className="text-slate-500">Rings:</span>
        <span className="text-slate-400">Inner = Exact</span>
        <span className="text-slate-400">Middle = Potential</span>
        <span className="text-slate-400">Outer = Hypothesis</span>
      </div>

      {/* Freshness Legend */}
      <div className="flex items-center gap-3">
        <span className="text-slate-500">Freshness:</span>
        <span className="flex items-center gap-1">
          <span
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: FRESHNESS_COLORS.fresh }}
          />
          <span className="text-slate-400">&le;6h</span>
        </span>
        <span className="flex items-center gap-1">
          <span
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: FRESHNESS_COLORS.stale }}
          />
          <span className="text-slate-400">6-24h</span>
        </span>
        <span className="flex items-center gap-1">
          <span
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: FRESHNESS_COLORS.old }}
          />
          <span className="text-slate-400">&gt;24h</span>
        </span>
      </div>
    </div>
  );
};
