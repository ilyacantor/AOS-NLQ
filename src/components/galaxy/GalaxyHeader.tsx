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
    <div className="flex items-center justify-between px-4 py-3 bg-slate-900/50 border-b border-slate-800">
      <div className="flex items-center gap-6 text-sm">
        <span className="text-slate-400">
          Confidence: <span className={`font-semibold ${confColor}`}>{confPercent}%</span>
        </span>
        <span className="text-slate-400">
          Quality: <span className={`font-semibold ${qualityColor}`}>{qualityPercent}%</span>
        </span>
        <span className="text-slate-400">
          <span className="text-white font-semibold">{nodeCount}</span> nodes
        </span>
      </div>
      {query && (
        <div className="text-sm text-slate-500 truncate max-w-md">
          "{query}"
        </div>
      )}
    </div>
  );
};
