import React from 'react';
import { Calendar, FlaskConical, AlertTriangle, CheckCircle2, TrendingUp } from 'lucide-react';

export default function KpiCards({ kpis }) {
  if (!kpis) return null;

  const formatDate = (dStr) => {
    if (!dStr) return '-';
    try {
      const [y, m, d] = dStr.split('-');
      const date = new Date(parseInt(y), parseInt(m) - 1, parseInt(d));
      return date.toLocaleDateString('es-CL', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch {
      return dStr;
    }
  };

  const cards = [
    {
      title: 'Tomas de Muestra',
      value: kpis.draw_count,
      sub: kpis.date_start && kpis.date_end ? `${formatDate(kpis.date_start)} — ${formatDate(kpis.date_end)}` : 'Sin fechas',
      icon: Calendar,
      color: 'text-cyan-400',
      bg: 'bg-cyan-500/10 border-cyan-500/20',
    },
    {
      title: 'Resultados Extraídos',
      value: kpis.total_observations,
      sub: `${kpis.unique_analytes} analitos únicos`,
      icon: FlaskConical,
      color: 'text-blue-400',
      bg: 'bg-blue-500/10 border-blue-500/20',
    },
    {
      title: 'Fuera de Rango',
      value: kpis.out_of_range_count,
      sub: kpis.out_of_range_count === 0 ? 'Todos dentro del rango de referencia' : 'Lecturas por encima o debajo de referencia',
      icon: kpis.out_of_range_count > 0 ? AlertTriangle : CheckCircle2,
      color: kpis.out_of_range_count > 0 ? 'text-amber-400' : 'text-emerald-400',
      bg: kpis.out_of_range_count > 0 ? 'bg-amber-500/10 border-amber-500/20' : 'bg-emerald-500/10 border-emerald-500/20',
    },
    {
      title: 'Estado de Verificación',
      value:
        kpis.verified_count === kpis.total_observations && kpis.total_observations > 0
          ? '100% Verificado'
          : `${kpis.verified_count || 0} / ${kpis.total_observations} confirmados`,
      sub:
        kpis.verified_count === kpis.total_observations && kpis.total_observations > 0
          ? 'Confirmado por revisión humana'
          : `${kpis.flagged_count || 0} con notas o cualitativos`,
      icon: CheckCircle2,
      color:
        kpis.verified_count === kpis.total_observations && kpis.total_observations > 0
          ? 'text-emerald-400'
          : 'text-cyan-400',
      bg:
        kpis.verified_count === kpis.total_observations && kpis.total_observations > 0
          ? 'bg-emerald-500/10 border-emerald-500/20'
          : 'bg-cyan-500/10 border-cyan-500/20',
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
      {cards.map((card, idx) => {
        const Icon = card.icon;
        return (
          <div
            key={idx}
            className="p-4 sm:p-5 rounded-2xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-sm relative overflow-hidden transition-all hover:border-slate-700/80 shadow-sm"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-slate-400">{card.title}</span>
              <div className={`p-2 rounded-xl border ${card.bg}`}>
                <Icon className={`h-4 w-4 ${card.color}`} />
              </div>
            </div>
            <div className="text-xl sm:text-2xl font-bold text-white tracking-tight">
              {card.value}
            </div>
            <p className="text-[11px] sm:text-xs text-slate-400 mt-1 truncate">
              {card.sub}
            </p>
          </div>
        );
      })}
    </div>
  );
}
