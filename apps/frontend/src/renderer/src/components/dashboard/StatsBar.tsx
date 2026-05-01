import { Calendar, Clock, CheckCircle, Stethoscope } from 'lucide-react'
import { useT } from '../../hooks/useT'

interface StatsBarProps {
  todayCount: number
  pendingCount: number
  completedCount: number
  appointmentCount: number
}

interface StatCardProps {
  label: string
  value: number
  icon: React.ReactNode
  colorClass: string
}

function StatCard({ label, value, icon, colorClass }: StatCardProps): React.JSX.Element {
  return (
    <div className="flex items-center gap-4 rounded-xl bg-white dark:bg-slate-800 p-5 shadow-sm ring-1 ring-slate-200/60 dark:ring-slate-700/60">
      <div className={`flex h-12 w-12 items-center justify-center rounded-lg ${colorClass}`}>
        {icon}
      </div>
      <div>
        <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
        <p className="text-2xl font-semibold text-slate-800 dark:text-slate-100">{value}</p>
      </div>
    </div>
  )
}

export function StatsBar({
  todayCount,
  pendingCount,
  completedCount,
  appointmentCount,
}: StatsBarProps): React.JSX.Element {
  const t = useT()
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
      <StatCard
        label={t('stats_todayAppts')}
        value={appointmentCount}
        icon={<Stethoscope className="h-6 w-6 text-purple-600" />}
        colorClass="bg-purple-50 dark:bg-purple-900/30"
      />
      <StatCard
        label={t('stats_todaySessions')}
        value={todayCount}
        icon={<Calendar className="h-6 w-6 text-blue-600" />}
        colorClass="bg-blue-50 dark:bg-blue-900/30"
      />
      <StatCard
        label={t('stats_pendingReview')}
        value={pendingCount}
        icon={<Clock className="h-6 w-6 text-amber-600" />}
        colorClass="bg-amber-50 dark:bg-amber-900/30"
      />
      <StatCard
        label={t('stats_completed')}
        value={completedCount}
        icon={<CheckCircle className="h-6 w-6 text-emerald-600" />}
        colorClass="bg-emerald-50 dark:bg-emerald-900/30"
      />
    </div>
  )
}
