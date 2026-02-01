import React from 'react';

interface GalaxyHeaderProps {
  confidence: number;
  dataQuality: number;
  nodeCount: number;
  query?: string;
}

export const GalaxyHeader: React.FC<GalaxyHeaderProps> = ({
  confidence,
  dataQuality,
  nodeCount,
  query
}) => {
  const confPercent = Math.round(confidence * 100);
  const qualityPercent = Math.round(dataQuality * 100);

  // Color confidence based on value
  const confColor = confPercent >= 85 ? 'text-green-400' :
                    confPercent >= 55 ? 'text-yellow-400' :
                    'text-red-400';

  const qualityColor = qualityPercent >= 90 ? 'text-green-400' :
                       qualityPercent >= 70 ? 'text-yellow-400' :
                       'text-red-400';

  return (
    <div className="flex items-center justify-between px-3 py-1.5 bg-slate-900/50 border-b border-slate-800">
      <div className="flex items-center gap-3 md:gap-4 text-xs">
        <span className="text-slate-500">
          Conf: <span className={`font-medium ${confColor}`}>{confPercent}%</span>
        </span>
        <span className="text-slate-500">
          Qual: <span className={`font-medium ${qualityColor}`}>{qualityPercent}%</span>
        </span>
        <span className="text-slate-500">
          <span className="text-slate-300 font-medium">{nodeCount}</span> nodes
        </span>
      </div>
      {query && (
        <div className="hidden md:block text-xs text-slate-600 truncate max-w-xs">
          "{query}"
        </div>
      )}
    </div>
  );
};
